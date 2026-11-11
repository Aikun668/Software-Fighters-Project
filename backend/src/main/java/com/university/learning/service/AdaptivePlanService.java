package com.university.learning.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Durable, rule-based rolling plans. No generated mastery and no unconfirmed edits. */
@Service
public class AdaptivePlanService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private boolean initialized;
    public AdaptivePlanService(JdbcTemplate jdbc, ObjectMapper mapper) { this.jdbc=jdbc; this.mapper=mapper; }
    private synchronized void init() {
        if(initialized) return;
        jdbc.execute("CREATE TABLE IF NOT EXISTS adaptive_plan (id VARCHAR(40) PRIMARY KEY,user_id BIGINT NOT NULL,version BIGINT NOT NULL,document_json LONGTEXT NOT NULL,undo_json LONGTEXT NULL,last_action VARCHAR(20) NOT NULL)");
        jdbc.execute("CREATE TABLE IF NOT EXISTS adaptive_plan_proposal (id VARCHAR(40) PRIMARY KEY,plan_id VARCHAR(40) NOT NULL,user_id BIGINT NOT NULL,document_json LONGTEXT NOT NULL)");
        initialized=true;
    }
    private ResponseStatusException error(HttpStatus code,String text) { return new ResponseStatusException(code,text); }
    private void require(boolean condition,String text) { if(!condition) throw error(HttpStatus.BAD_REQUEST,text); }
    private String id() { return UUID.randomUUID().toString(); }
    private ObjectNode parse(String json) { try { return (ObjectNode)mapper.readTree(json); } catch(Exception e) { throw new IllegalStateException("Invalid stored plan",e); } }
    private String text(JsonNode n,String field,int max,boolean required) { String s=n.path(field).asText("").trim(); require((!required||!s.isBlank())&&s.length()<=max,field+" 内容不能为空或过长"); return s; }
    private int minutes(JsonNode n,String field,int fallback) { JsonNode v=n.get(field); if(v==null) return fallback; require(v.isIntegralNumber()&&v.canConvertToInt()&&v.asInt()>0&&v.asInt()<=480,field+" 必须为 1–480 分钟"); return v.asInt(); }
    private String deadline(JsonNode n) { String d=n.path("deadline").asText(""); if(d.isBlank())return null; try { LocalDate.parse(d); } catch(Exception e) { throw error(HttpStatus.BAD_REQUEST,"期限必须为 YYYY-MM-DD"); } return d; }
    private void version(ObjectNode plan,JsonNode request) { require(request.path("version").isIntegralNumber()&&request.path("version").canConvertToLong()&&request.path("version").asLong()>0,"需要计划版本"); if(plan.path("version").asLong()!=request.path("version").asLong())throw error(HttpStatus.CONFLICT,"计划已更新，请刷新后重试"); }
    private List<ObjectNode> tasks(ObjectNode p) { List<ObjectNode> result=new ArrayList<>(); p.path("modules").forEach(m->m.path("tasks").forEach(t->result.add((ObjectNode)t))); return result; }
    private ObjectNode decorate(ObjectNode p,boolean undo) {
        ArrayNode next=mapper.createArrayNode(); tasks(p).stream().filter(t->!Set.of("completed","deferred").contains(t.path("status").asText())).limit(3).forEach(next::add);
        boolean unrefined=false;for(JsonNode m:p.path("modules"))if(m.path("tasks").isEmpty())unrefined=true;
        String due=p.path("deadline").asText("");int remaining=tasks(p).stream().filter(t->!Set.of("completed","deferred").contains(t.path("status").asText())).mapToInt(t->t.path("minutes").asInt()).sum();
        String warning=null;if(!due.isBlank()){long capacity=Math.max(0,ChronoUnit.DAYS.between(LocalDate.now(),LocalDate.parse(due))+1)*p.path("dailyMinutes").asInt();if(remaining>capacity)warning="期限内可用 "+capacity+" 分钟，剩余任务需要 "+remaining+" 分钟。请提出调整并明确延长期限或延期任务。";}
        p.put("capacityWarning",warning);p.set("nextTasks",next);p.put("canUndo",undo);p.put("status",!unrefined&&tasks(p).stream().allMatch(t->"completed".equals(t.path("status").asText()))?"completed":"in_progress");return p;
    }
    public List<ObjectNode> list(long user) { init();return jdbc.query("SELECT document_json,last_action FROM adaptive_plan WHERE user_id=? ORDER BY id",(rs,i)->decorate(parse(rs.getString(1)),"apply".equals(rs.getString(2))),user); }
    public ObjectNode get(long user,String id) { init();var rows=jdbc.query("SELECT document_json,last_action FROM adaptive_plan WHERE user_id=? AND id=?",(rs,i)->decorate(parse(rs.getString(1)),"apply".equals(rs.getString(2))),user,id);if(rows.isEmpty())throw error(HttpStatus.NOT_FOUND,"计划不存在");return rows.get(0); }
    public ObjectNode create(long user,JsonNode body) {
        require(body!=null&&body.isObject(),"需要计划对象");
        init(); ObjectNode p=mapper.createObjectNode();p.put("id",id());p.put("title",text(body,"title",160,true));p.put("goal",text(body,"goal",2000,true));p.put("dailyMinutes",minutes(body,"dailyMinutes",30));p.put("deadline",deadline(body));p.put("version",1);p.set("history",mapper.createArrayNode());
        JsonNode modules=body.path("modules");require(modules.isArray()&&modules.size()>0&&modules.size()<=20,"需要 1–20 个模块");ArrayNode ms=p.putArray("modules");int count=0;
        for(JsonNode m:modules) { ObjectNode module=ms.addObject();module.put("id",id());module.put("title",text(m,"title",160,true));ArrayNode ts=module.putArray("tasks");require(m.path("tasks").isArray(),"模块需要 tasks 数组");for(JsonNode t:m.path("tasks")){count++;require(count<=100,"最多 100 个任务");ObjectNode task=ts.addObject();task.put("id",id());task.put("title",text(t,"title",300,true));task.put("minutes",minutes(t,"minutes",20));task.put("status","pending");task.put("checkpoint","");task.put("nextAction",text(t,"nextAction",1000,false));} }
        require(count>0,"至少一个近期任务");decorate(p,false);jdbc.update("INSERT INTO adaptive_plan(id,user_id,version,document_json,last_action) VALUES(?,?,?,?,?)",p.path("id").asText(),user,1,p.toString(),"create");return p;
    }
    private ObjectNode save(long user,ObjectNode p,long expected,String action,String undo) {
        p.put("version",expected+1);decorate(p,"apply".equals(action));int changed=jdbc.update("UPDATE adaptive_plan SET document_json=?,version=?,last_action=?,undo_json=? WHERE id=? AND user_id=? AND version=?",p.toString(),expected+1,action,undo,p.path("id").asText(),user,expected);if(changed!=1)throw error(HttpStatus.CONFLICT,"计划已更新，请刷新后重试");return p;
    }
    public ObjectNode addTask(long user,String planId,String moduleId,JsonNode body) {
        ObjectNode p=get(user,planId);version(p,body);require(tasks(p).size()<100,"最多 100 个任务");
        ObjectNode module=null;for(JsonNode m:p.path("modules"))if(moduleId.equals(m.path("id").asText()))module=(ObjectNode)m;
        if(module==null)throw error(HttpStatus.NOT_FOUND,"模块不存在");
        ObjectNode task=mapper.createObjectNode();task.put("id",id());task.put("title",text(body,"title",300,true));task.put("minutes",minutes(body,"minutes",20));task.put("nextAction",text(body,"nextAction",1000,false));task.put("checkpoint","");task.put("status","pending");((ArrayNode)module.path("tasks")).add(task);
        return save(user,p,p.path("version").asLong(),"refine",null);
    }
    public ObjectNode updateTask(long user,String planId,String taskId,JsonNode body) {
        ObjectNode p=get(user,planId);version(p,body);ObjectNode task=tasks(p).stream().filter(t->taskId.equals(t.path("id").asText())).findFirst().orElseThrow(()->error(HttpStatus.NOT_FOUND,"任务不存在"));
        if(body.has("status")){String s=body.path("status").asText();require(Set.of("pending","in_progress","paused","blocked","completed").contains(s),"无效任务状态");task.put("status",s);}
        if(body.has("checkpoint"))task.put("checkpoint",text(body,"checkpoint",2000,false));if(body.has("nextAction"))task.put("nextAction",text(body,"nextAction",1000,false));return save(user,p,p.path("version").asLong(),"progress",null);
    }
    /** 关键词前面 3 个字以内出现否定词，就把这次提及当作"否认"，不算一次调整意图。 */
    private static final Pattern NEGATED = Pattern.compile("(?:不|没|没有|别|无需|不要|不用|非|勿)[^，。；！？,.!?;、\\s]{0,3}$");
    /** 每日时间预算：只在"每天/每日/daily/一天 + 数字 + 分钟"时才算，且不能是"某一天我用了 20 分钟"这类已发生用量。 */
    private static final Pattern DAILY_BUDGET = Pattern.compile("(?:每天|每日|daily|(?<!某)一天)[^0-9]{0,8}(\\d{1,3})\\s*(?:分钟|min)");
    private static final Pattern PAST_USAGE = Pattern.compile("用了|花了|学了|做了|已经|昨天|前天|上次|总共");
    /** 判断一句话是否真的提出了某个意图（"不延期""没有卡住"不算）。 */
    private boolean asserts(String message,String... keywords) {
        for(String keyword:keywords) { int from=0; while(true) { int at=message.indexOf(keyword,from); if(at<0) break; if(!NEGATED.matcher(message.substring(0,at)).find()) return true; from=at+keyword.length(); } }
        return false;
    }
    private boolean mentions(String message,String... keywords) { for(String keyword:keywords) if(message.contains(keyword)) return true; return false; }
    /** 从正文里读出每日分钟数；读不到或只是复述历史用量时返回 null。 */
    private Integer budgetFromMessage(String message) {
        Matcher m=DAILY_BUDGET.matcher(message);
        while(m.find()) { if(!PAST_USAGE.matcher(m.group()).find()) { int value=Integer.parseInt(m.group(1)); require(value>0&&value<=480,"每天时间必须为 1–480 分钟"); return value; } }
        return null;
    }
    public ObjectNode propose(long user,String planId,JsonNode body) {
        ObjectNode p=get(user,planId);version(p,body);String message=text(body,"message",2000,true);ObjectNode candidate=p.deepCopy();ObjectNode proposal=mapper.createObjectNode();proposal.put("id",id());proposal.put("baseVersion",p.path("version").asLong());proposal.put("evaluatedDate",LocalDate.now().toString());proposal.put("message",message);ArrayNode changes=proposal.putArray("changes");
        int budget=minutes(body,"dailyMinutes",p.path("dailyMinutes").asInt());Integer saidBudget=budgetFromMessage(message);boolean recognizedBudget=saidBudget!=null;if(!body.has("dailyMinutes")&&recognizedBudget)budget=saidBudget;candidate.put("dailyMinutes",budget);
        if(body.has("deadline"))candidate.put("deadline",deadline(body));
        boolean defer=asserts(message,"延期","推迟"),blocked=asserts(message,"卡住","不懂","没懂"),split=asserts(message,"拆分","拆开");
        require(!(defer&&blocked),"同一句里同时提到延期和卡点，请分开提出。先明确要延期，还是先记录卡点。");
        // 只有当用户真的调整了每日时间、或明确要求拆分时才重排任务；
        // 报卡点 / 只改截止日期不再顺手把超长任务拆开，也不会覆盖断点。
        boolean budgetChanged=body.has("dailyMinutes")||recognizedBudget||budget!=p.path("dailyMinutes").asInt();boolean allowSplit=split||budgetChanged;boolean changed=false;
        String target=body.path("taskId").asText("");
        require(target.isBlank()||tasks(p).stream().anyMatch(t->target.equals(t.path("id").asText())),"目标任务不存在");
        require(body.has("dailyMinutes")||body.has("deadline")||recognizedBudget||budget!=p.path("dailyMinutes").asInt()||defer||blocked||split,mentions(message,"延期","推迟","拆分","拆开","卡住","不懂","没懂")?"检测到否定指令，未生成更改。请明确要修改的部分。":"暂支持每天分钟数、卡点、拆分或延期。请明确调整内容。");
        for(JsonNode module:candidate.path("modules")){ArrayNode out=mapper.createArrayNode();for(JsonNode raw:module.path("tasks")){ObjectNode task=(ObjectNode)raw;ObjectNode before=task.deepCopy();String kind="keep";
            boolean unfinished=!"completed".equals(task.path("status").asText())&&!"deferred".equals(task.path("status").asText());
            if(unfinished&&(target.isBlank()||target.equals(task.path("id").asText()))){
                if(defer&&!changed){task.put("status","deferred");kind="defer";changed=true;}
                else if(blocked&&!changed){task.put("status","blocked");task.put("checkpoint",message);task.put("nextAction","先针对卡点做一个具体例子，再继续原任务");kind="checkpoint";changed=true;}
                if(allowSplit&&task.path("minutes").asInt()>budget){int total=task.path("minutes").asInt();int parts=(total+budget-1)/budget;require(parts<=30,"拆分过细，请提高每天时间");ArrayNode splitParts=mapper.createArrayNode();for(int i=0;i<parts;i++){ObjectNode part=task.deepCopy();if(i>0){part.put("id",id());part.put("status","pending");part.put("checkpoint","");}part.put("title",before.path("title").asText()+" · "+(i+1)+"/"+parts);part.put("minutes",Math.min(budget,total-i*budget));out.add(part);splitParts.add(part.deepCopy());}kind="split";ObjectNode diff=changes.addObject();diff.put("kind",kind);diff.put("taskId",task.path("id").asText());diff.set("before",before);diff.set("after",splitParts);continue;}
            }out.add(task);if(!"keep".equals(kind)){ObjectNode diff=changes.addObject();diff.put("kind",kind);diff.put("taskId",task.path("id").asText());diff.set("before",before);diff.set("after",task.deepCopy());}}((ObjectNode)module).set("tasks",out);}
        if((defer||blocked)&&!changed)throw error(HttpStatus.BAD_REQUEST,(defer?"延期":"记录卡点")+"需要至少一个未完成的任务；当前没有可调整的任务。");
        // 确认稿里也要明确列出每日时间与期限的变化，避免"只看到一堆保留行"。
        if(budget!=p.path("dailyMinutes").asInt()){ObjectNode diff=changes.addObject();diff.put("kind","budget");diff.put("before",p.path("dailyMinutes").asInt());diff.put("after",budget);}
        if(body.has("deadline")&&!candidate.path("deadline").asText("").equals(p.path("deadline").asText(""))){ObjectNode diff=changes.addObject();diff.put("kind","deadline");diff.put("before",p.path("deadline").asText(""));diff.put("after",candidate.path("deadline").asText(""));}
        require(tasks(candidate).size()<=100,"拆分后超过 100 个任务，请提高每天时间");String d=candidate.path("deadline").asText("");String conflict=null;if(!d.isBlank()){long available=Math.max(0,ChronoUnit.DAYS.between(LocalDate.now(),LocalDate.parse(d))+1)*budget;int remaining=tasks(candidate).stream().filter(t->!Set.of("completed","deferred").contains(t.path("status").asText())).mapToInt(t->t.path("minutes").asInt()).sum();if(remaining>available)conflict="剩余 "+remaining+" 分钟，期限内只有 "+available+" 分钟。请明确延长期限，或取消并重新提出延期任务方案。";}
        proposal.put("conflict",conflict);
        if(conflict!=null){int remaining=tasks(candidate).stream().filter(t->!Set.of("completed","deferred").contains(t.path("status").asText())).mapToInt(t->t.path("minutes").asInt()).sum();proposal.put("extendedDeadline",LocalDate.now().plusDays(Math.max(0,(remaining+budget-1)/budget-1)).toString());ArrayNode deferred=proposal.putArray("deferredTasks");long capacity=Math.max(0,ChronoUnit.DAYS.between(LocalDate.now(),LocalDate.parse(d))+1)*budget;for(ObjectNode task:tasks(candidate)){if(Set.of("completed","deferred").contains(task.path("status").asText()))continue;if(task.path("minutes").asInt()<=capacity)capacity-=task.path("minutes").asInt();else deferred.add(task.deepCopy());}}
        proposal.put("engine","rules-v1");proposal.set("proposedPlan",decorate(candidate,false));jdbc.update("INSERT INTO adaptive_plan_proposal(id,plan_id,user_id,document_json) VALUES(?,?,?,?)",proposal.path("id").asText(),planId,user,proposal.toString());return proposal;
    }
    public ObjectNode apply(long user,String planId,String proposalId,JsonNode body) {
        ObjectNode current=get(user,planId);version(current,body);var rows=jdbc.query("SELECT document_json FROM adaptive_plan_proposal WHERE id=? AND plan_id=? AND user_id=?",(rs,i)->parse(rs.getString(1)),proposalId,planId,user);if(rows.isEmpty())throw error(HttpStatus.NOT_FOUND,"调整建议不存在");ObjectNode proposal=rows.get(0);if(!LocalDate.now().toString().equals(proposal.path("evaluatedDate").asText()))throw error(HttpStatus.CONFLICT,"日期已变化，请重新生成调整预览");if(current.path("version").asLong()!=proposal.path("baseVersion").asLong())throw error(HttpStatus.CONFLICT,"建议已过期，请重新生成");ObjectNode candidate=((ObjectNode)proposal.path("proposedPlan")).deepCopy();
        String proposedDeadline=candidate.path("deadline").asText("");
        long capacityNow=proposedDeadline.isBlank()?Long.MAX_VALUE:Math.max(0,ChronoUnit.DAYS.between(LocalDate.now(),LocalDate.parse(proposedDeadline))+1)*candidate.path("dailyMinutes").asInt();
        int remainingNow=tasks(candidate).stream().filter(t->!Set.of("completed","deferred").contains(t.path("status").asText())).mapToInt(t->t.path("minutes").asInt()).sum();
        if(remainingNow>capacityNow){require(Set.of("extend","defer").contains(body.path("resolution").asText()),"需要明确选择延长期限或延期未完成任务");int remaining=tasks(candidate).stream().filter(t->!Set.of("completed","deferred").contains(t.path("status").asText())).mapToInt(t->t.path("minutes").asInt()).sum();if("extend".equals(body.path("resolution").asText())) candidate.put("deadline",LocalDate.now().plusDays(Math.max(0,(remaining+candidate.path("dailyMinutes").asInt()-1)/candidate.path("dailyMinutes").asInt()-1)).toString());
            else { long capacity=Math.max(0,ChronoUnit.DAYS.between(LocalDate.now(),LocalDate.parse(candidate.path("deadline").asText()))+1)*candidate.path("dailyMinutes").asInt(); for(ObjectNode t:tasks(candidate)){ if(Set.of("completed","deferred").contains(t.path("status").asText()))continue; if(t.path("minutes").asInt()<=capacity)capacity-=t.path("minutes").asInt();else t.put("status","deferred"); } }
        }
        ArrayNode history=(ArrayNode)candidate.path("history");history.addObject().put("proposalId",proposalId).put("message",proposal.path("message").asText()).put("action","apply");if(history.size()>50)history.remove(0);return save(user,candidate,current.path("version").asLong(),"apply",current.toString());
    }
    public ObjectNode undo(long user,String planId,JsonNode body) {
        ObjectNode current=get(user,planId);version(current,body);var rows=jdbc.query("SELECT undo_json FROM adaptive_plan WHERE id=? AND user_id=? AND last_action='apply'",(rs,i)->rs.getString(1),planId,user);if(rows.isEmpty()||rows.get(0)==null)throw error(HttpStatus.CONFLICT,"没有可撤销调整；新进度保存后不可覆盖");ObjectNode previous=parse(rows.get(0));ArrayNode history=(ArrayNode)current.path("history");history.addObject().put("action","undo");previous.set("history",history);return save(user,previous,current.path("version").asLong(),"undo",null);
    }
}

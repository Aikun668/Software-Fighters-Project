package com.university.learning.service;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.web.server.ResponseStatusException;
import java.util.*;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;
class AdaptivePlanIndependentReviewTest {
 final ObjectMapper json=new ObjectMapper();
 final JdbcTemplate jdbc=new JdbcTemplate(new DriverManagerDataSource("jdbc:h2:mem:review_"+UUID.randomUUID()+";MODE=MySQL;DB_CLOSE_DELAY=-1","sa",""));
 final AdaptivePlanService s=new AdaptivePlanService(jdbc,json);
 JsonNode b(String v)throws Exception{return json.readTree(v);}
 ObjectNode create()throws Exception{return s.create(1,b("{\"title\":\"事务\",\"goal\":\"运行幻读例子\",\"dailyMinutes\":20,\"modules\":[{\"title\":\"当前\",\"tasks\":[{\"title\":\"例子\",\"minutes\":40}]},{\"title\":\"后续\",\"tasks\":[]}]}"));}
 String task(ObjectNode p){return p.path("modules").get(0).path("tasks").get(0).path("id").asText();}
 @Test void concurrentSameVersionHasExactlyOneWinner()throws Exception {
  var p=create();String id=p.path("id").asText();var gate=new CountDownLatch(1);var pool=Executors.newFixedThreadPool(2);
  try {List<Future<Integer>> results=new ArrayList<>();for(String state:List.of("paused","completed"))results.add(pool.submit(()->{gate.await();try{s.updateTask(1,id,task(p),b("{\"version\":1,\"status\":\""+state+"\"}"));return 200;}catch(ResponseStatusException e){return e.getStatusCode().value();}}));gate.countDown();List<Integer> statuses=new ArrayList<>();for(var r:results)statuses.add(r.get(10,TimeUnit.SECONDS));Collections.sort(statuses);assertEquals(List.of(200,409),statuses);assertEquals(2,s.get(1,id).path("version").asInt());}finally{pool.shutdownNow();}
 }
 @Test void everyWriteChecksOwner()throws Exception{
  var p=create();String id=p.path("id").asText(),module=p.path("modules").get(1).path("id").asText();var pr=s.propose(1,id,b("{\"version\":1,\"message\":\"拆分\"}"));
  assertEquals(404,assertThrows(ResponseStatusException.class,()->s.updateTask(2,id,task(p),b("{\"version\":1,\"status\":\"completed\"}"))).getStatusCode().value());
  assertEquals(404,assertThrows(ResponseStatusException.class,()->s.addTask(2,id,module,b("{\"version\":1,\"title\":\"x\"}"))).getStatusCode().value());
  assertEquals(404,assertThrows(ResponseStatusException.class,()->s.propose(2,id,b("{\"version\":1,\"message\":\"延期\"}"))).getStatusCode().value());
  assertEquals(404,assertThrows(ResponseStatusException.class,()->s.apply(2,id,pr.path("id").asText(),b("{\"version\":1}"))).getStatusCode().value());
  assertEquals(404,assertThrows(ResponseStatusException.class,()->s.undo(2,id,b("{\"version\":1}"))).getStatusCode().value());assertEquals(p,s.get(1,id));
 }
 @Test void emptyFutureModuleRemainsOpenAndRefinable()throws Exception{
  var p=create();String id=p.path("id").asText(),module=p.path("modules").get(1).path("id").asText();var done=s.updateTask(1,id,task(p),b("{\"version\":1,\"status\":\"completed\"}"));assertNotEquals("completed",done.path("status").asText());var refined=s.addTask(1,id,module,b("{\"version\":2,\"title\":\"下一步\",\"minutes\":15}"));assertEquals("下一步",refined.path("nextTasks").get(0).path("title").asText());assertEquals("completed",refined.path("modules").get(0).path("tasks").get(0).path("status").asText());
 }
 @Test void yesterdayProposalMustBeRepreviewed()throws Exception {
  var p=create();String id=p.path("id").asText();var pr=s.propose(1,id,b("{\"version\":1,\"message\":\"拆分\"}"));pr.put("evaluatedDate","2000-01-01");jdbc.update("UPDATE adaptive_plan_proposal SET document_json=? WHERE id=?",pr.toString(),pr.path("id").asText());assertEquals(409,assertThrows(ResponseStatusException.class,()->s.apply(1,id,pr.path("id").asText(),b("{\"version\":1}"))).getStatusCode().value());assertEquals(p,s.get(1,id));
 }
}

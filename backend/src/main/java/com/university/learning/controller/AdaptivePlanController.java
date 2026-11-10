package com.university.learning.controller;
import com.fasterxml.jackson.databind.JsonNode;
import com.university.learning.common.Result;
import com.university.learning.service.AdaptivePlanService;
import com.university.learning.utils.UserHolder;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
@RestController
@RequestMapping("/api/adaptive-plans")
public class AdaptivePlanController {
    private final AdaptivePlanService service;
    public AdaptivePlanController(AdaptivePlanService service){this.service=service;}
    private long user(){if(UserHolder.getUser()==null||UserHolder.getUser().getId()==null)throw new ResponseStatusException(HttpStatus.UNAUTHORIZED,"请先登录");return UserHolder.getUser().getId();}
    @GetMapping public Result list(){return Result.ok(service.list(user()));}
    @PostMapping public Result create(@RequestBody JsonNode body){return Result.ok(service.create(user(),body));}
    @GetMapping("/{id}") public Result get(@PathVariable String id){return Result.ok(service.get(user(),id));}
    @PostMapping("/{id}/modules/{moduleId}/tasks") public Result addTask(@PathVariable String id,@PathVariable String moduleId,@RequestBody JsonNode body){return Result.ok(service.addTask(user(),id,moduleId,body));}
    @PatchMapping("/{id}/tasks/{taskId}") public Result task(@PathVariable String id,@PathVariable String taskId,@RequestBody JsonNode body){return Result.ok(service.updateTask(user(),id,taskId,body));}
    @PostMapping("/{id}/proposals") public Result propose(@PathVariable String id,@RequestBody JsonNode body){return Result.ok(service.propose(user(),id,body));}
    @PostMapping("/{id}/proposals/{proposalId}/apply") public Result apply(@PathVariable String id,@PathVariable String proposalId,@RequestBody JsonNode body){return Result.ok(service.apply(user(),id,proposalId,body));}
    @PostMapping("/{id}/undo") public Result undo(@PathVariable String id,@RequestBody JsonNode body){return Result.ok(service.undo(user(),id,body));}
}

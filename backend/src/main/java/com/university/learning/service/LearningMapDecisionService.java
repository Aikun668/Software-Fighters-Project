package com.university.learning.service;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import java.time.LocalDateTime;
import java.util.*;

/** Only explicit user decisions are stored. Derived candidates remain revocable with their sources. */
@Service
public class LearningMapDecisionService {
    private final JdbcTemplate jdbc;
    private boolean initialized;
    public LearningMapDecisionService(JdbcTemplate jdbc) { this.jdbc = jdbc; }
    private synchronized void initialize() {
        if (initialized) return;
        jdbc.execute("CREATE TABLE IF NOT EXISTS learning_map_decision (user_id BIGINT NOT NULL, suggestion_id VARCHAR(80) NOT NULL, decision VARCHAR(16) NOT NULL, updated_at TIMESTAMP NOT NULL, PRIMARY KEY(user_id,suggestion_id))");
        initialized=true;
    }
    public Map<String,String> read(Long user) {
        initialize();
        Map<String,String> result=new HashMap<>();
        jdbc.query("SELECT suggestion_id,decision FROM learning_map_decision WHERE user_id=?", rs -> { result.put(rs.getString(1),rs.getString(2)); }, user);
        return result;
    }
    public synchronized void save(Long user,String id,String decision) {
        if (!Set.of("accepted","rejected").contains(decision)) throw new IllegalArgumentException("Invalid decision");
        initialize();
        if (jdbc.update("UPDATE learning_map_decision SET decision=?,updated_at=? WHERE user_id=? AND suggestion_id=?",decision,LocalDateTime.now(),user,id)==0)
            jdbc.update("INSERT INTO learning_map_decision(user_id,suggestion_id,decision,updated_at) VALUES(?,?,?,?)",user,id,decision,LocalDateTime.now());
    }
}

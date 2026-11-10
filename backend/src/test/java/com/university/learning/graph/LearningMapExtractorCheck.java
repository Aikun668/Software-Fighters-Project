package com.university.learning.graph;
import java.util.*;
/** Dependency-free contract checks: javac + java -ea. */
public class LearningMapExtractorCheck {
    public static void main(String[] args) {
        var e = new LearningMapExtractor();
        e.observe("1", "1", "我正在学习线性代数", "2026-01-01");
        e.observe("1", "2", "什么是机器学习？", "2026-01-02");
        check(e.nodes().size() == 2, "two explicit topics");
        check(e.edges().isEmpty(), "cooccurrence is not relationship");
        e.observe("1", "3", "机器学习依赖线性代数", "2026-01-03");
        check(e.edges().size() == 1, "explicit relationship");
        e.observe("1", "4", "机器学习不依赖概率论", "2026-01-04");
        e.observe("1", "5", "机器学习依赖概率论吗？", "2026-01-04");
        check(e.edges().size() == 1, "negation and questions not assertions");
        e.observe("2", "6", "我正在学习线性代数", "2026-01-05");
        check(e.nodes().size() == 2, "same concept deduplicated");
        check(e.nodes().get(0).sources().size() == 3, "all source turns retained");
        var empty = new LearningMapExtractor();
        empty.observe("1", "9", "你好，今天天气不错", "");
        check(empty.nodes().isEmpty(), "small talk empty");
        empty.observe("1", "10", "[[量子计算]]和[[音乐]]", "");
        check(empty.nodes().size() == 2 && empty.edges().isEmpty(), "explicit tags stay isolated");
        empty.observe("1", "11", "学习" + "字".repeat(20000), "");
        check(empty.nodes().size() == 2, "huge input skipped");
        System.out.println("LearningMapExtractorCheck: 9 checks passed");
    }
    static void check(boolean yes, String message) { if (!yes) throw new AssertionError(message); }
}

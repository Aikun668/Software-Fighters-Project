# Learning map backend acceptance

Run the ordinary backend tests with JDK 17 and Maven. `LearningMapIntegrationTest` uses an isolated H2 database, the production map controller/extractor, `AgentMemoryService`, and `LearningMapDecisionService`. Its conversation/message adapters read actual SQL rows; they are not precomputed API responses. Test-only identity uses `X-Test-User`, not production login or Redis authentication.

```sh
mvn -Dtest='LearningMap*Test' test
```

In restricted Linux containers where Mockito cannot self-attach, use the installed Byte Buddy agent at JVM startup, e.g. `-DargLine=-javaagent:/path/to/byte-buddy-agent.jar`. Do not disable authentication or add invented production credentials to make application-context tests pass.

## Browser transport without a listening port

```sh
mvn -DskipTests test-compile dependency:build-classpath -Dmdep.outputFile=target/test-classpath.txt -Dmdep.includeScope=test
java -cp "target/test-classes:target/classes:$(cat target/test-classpath.txt)" com.university.learning.graph.LearningMapBrowserBridge
```

This test-only main prints `MAP_READY`, accepts one JSON object per stdin line and returns `MAP_RESULT {"status":...,"body":...}` per request. Ignore ordinary logging lines. Request shape:

```json
{"method":"GET","path":"/api/learning-map","user":"1"}
```

`user` is `1`, `2`, or `anonymous`; default is the explicit fixture user `1`. `body` is an optional JSON object. Only `/api/learning-map` routes are exposed. The fixture seeds four public test learning nodes, two suggestions and four trajectory events for user 1, and a separate node for user 2. There is no external network listener. It is NOT a deployed preview, production authentication test, MySQL migration verification, or evidence of real LLM calls.

The H2 fixture is ephemeral. Production decisions use `learning_map_decision` in the existing application JDBC database, keyed by authenticated user and suggestion ID. Current source visibility is revalidated before a decision or continuation; a stored decision does not resurrect a forgotten source. Accepted relationships are labeled `user_confirmed`, never `depends_on`.

Practice trajectory entries currently reflect explicit chat requests or self-reports, not verified exercise submissions. The small bridge catalogue is transparent and intentionally incomplete. No AI-generated relationship is presented as established knowledge.

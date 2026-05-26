"""
AI internal HTTP API

Only exposed to Java backend via localhost.
Not accessible from outside.

Routes:
  POST /internal/profile/chat        SSE streaming profile dialog
  POST /internal/resources/generate  SSE streaming resource generation
  POST /internal/tutor/chat          SSE streaming tutoring Q&A
  GET  /internal/path/{student_id}   Learning path JSON
"""

import json
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse

app = FastAPI(title="AI Microservice", docs_url=None, redoc_url=None)


@app.post("/internal/profile/chat")
async def profile_chat(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    student_id = body.get("student_id", "")

    async def event_stream():
        # TODO: replace with ProfileAgent streaming
        yield f"data: {json.dumps({'type': 'token', 'content': 'Hello!'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/internal/resources/generate")
async def resources_generate(request: Request):
    body = await request.json()
    student_id = body.get("student_id", "")
    topic = body.get("topic", "")

    async def event_stream():
        # TODO: replace with ResourceGenWorkflow
        yield f"data: {json.dumps({'type': 'progress', 'stage': 'outline'})}\n\n"
        yield f"data: {json.dumps({'type': 'progress', 'stage': 'generating'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/internal/tutor/chat")
async def tutor_chat(request: Request):
    body = await request.json()
    messages = body.get("messages", [])

    async def event_stream():
        # TODO: replace with TutorAgent
        yield f"data: {json.dumps({'type': 'token', 'content': 'Answer...'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/internal/path/{student_id}")
async def learning_path(student_id: str):
    # TODO: replace with LearningPathWorkflow
    return JSONResponse({"student_id": student_id, "steps": []})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)

"""Chat routes — the main conversation interface."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from futureself.orchestrator import run_turn
from futureself.web.templates_config import templates
from futureself.web.session import get_blueprint, get_token

router = APIRouter()


@router.get("/chat", response_class=HTMLResponse, response_model=None)
async def chat_page(request: Request):
    """Render the chat interface, or redirect to onboarding if no session."""
    token = get_token(request)
    if not token:
        return RedirectResponse("/", status_code=303)

    history = request.app.state.conversations.get(token, [])
    return templates.TemplateResponse(request, "chat.html", {"history": history})


@router.post("/chat/send", response_class=HTMLResponse, response_model=None)
async def chat_send(
    request: Request,
    message: str = Form(...),
):
    """Process a user message through the orchestrator and return the reply fragment."""
    token = get_token(request)
    if not token:
        return RedirectResponse("/", status_code=303)

    blueprint = get_blueprint(request)
    if not blueprint:
        return RedirectResponse("/", status_code=303)

    result = await run_turn(blueprint, message)

    # Update session state
    request.app.state.sessions[token] = result.updated_blueprint
    conversation = request.app.state.conversations.setdefault(token, [])
    conversation.append({"role": "user", "content": message})
    conversation.append({"role": "assistant", "content": result.user_facing_reply})

    return templates.TemplateResponse(
        request,
        "partials/chat_turn.html",
        {"user_message": message, "assistant_reply": result.user_facing_reply},
    )

"""Onboarding routes — first-time user setup flow."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from futureself.schemas import BioData, ContextData, PsychData, UserBlueprint
from futureself.web.templates_config import templates
from futureself.web.session import create_session, get_token

router = APIRouter()


@router.get("/", response_class=HTMLResponse, response_model=None)
async def onboard_step1_page(request: Request):
    """Show onboarding step 1, or redirect to chat if already set up."""
    if get_token(request):
        return RedirectResponse("/chat", status_code=303)
    return templates.TemplateResponse(request, "onboard_step1.html")


@router.post("/onboard/step1", response_class=HTMLResponse)
async def onboard_step1_submit(
    request: Request,
    age: int = Form(...),
    sex: str = Form(...),
    height_cm: float | None = Form(None),
    weight_kg: float | None = Form(None),
) -> HTMLResponse:
    """Receive step 1 data and render step 2 with step 1 as hidden fields."""
    return templates.TemplateResponse(
        request,
        "onboard_step2.html",
        {"age": age, "sex": sex, "height_cm": height_cm or "", "weight_kg": weight_kg or ""},
    )


@router.post("/onboard/complete")
async def onboard_complete(
    request: Request,
    # Step 1 fields (hidden)
    age: int = Form(...),
    sex: str = Form(...),
    height_cm: float | None = Form(None),
    weight_kg: float | None = Form(None),
    # Step 2 fields
    goals: str = Form(""),
    stress_level: str = Form("medium"),
    location_city: str = Form(""),
    location_country: str = Form(""),
    occupation: str = Form(""),
) -> RedirectResponse:
    """Create the user blueprint and session, then redirect to chat."""
    goals_list = [g.strip() for g in goals.split(",") if g.strip()]

    blueprint = UserBlueprint(
        bio=BioData(
            age=age,
            sex=sex,
            height_cm=height_cm if height_cm else None,
            weight_kg=weight_kg if weight_kg else None,
        ),
        psych=PsychData(
            goals=goals_list,
            stress_level=stress_level if stress_level in ("low", "medium", "high") else "medium",
        ),
        context=ContextData(
            location_city=location_city or None,
            location_country=location_country or None,
            occupation=occupation or None,
        ),
    )

    token = create_session(request.app.state, blueprint)

    response = RedirectResponse("/chat", status_code=303)
    response.set_cookie("fs_session", token, httponly=True, samesite="lax")
    return response

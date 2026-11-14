"""AI Health Coach for Indian Diets - Streamlit app. Run: streamlit run app.py"""
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from hc import ai, calc, db, foods, packaged, rag, state

st.set_page_config(page_title="AI Health Coach", page_icon="🥗", layout="wide")
st.markdown("""<style>
.block-container{padding-top:1.5rem;max-width:1200px}
div[data-testid="stMetric"]{background:rgba(128,128,128,.08);border-radius:10px;padding:10px 14px}
</style>""", unsafe_allow_html=True)

COLORS = {"protein": "#2a9d8f", "carbs": "#e9a23b", "fat": "#e76f51", "sugar": "#9b5de5"}
MEAL_TYPES = ["Breakfast", "Lunch", "Snack", "Dinner"]


@st.cache_data
def food_db():
    return foods.load_foods()


def show_disclaimer():
    st.warning(calc.DISCLAIMER, icon="⚠️")


def show_target_warnings(t: calc.Targets):
    for level, msg in t.warnings:
        {"error": st.error, "warning": st.warning, "info": st.info}[level](msg)


current_profile = state.current_profile


# ---------------------------------------------------------------- Profile
def page_profile(existing):
    st.title("Your profile" if existing else "Welcome! Let's set up your profile")
    if not existing:
        st.write("This stays on your computer (SQLite). It is used to calculate your calorie and macro targets.")
    e = existing or {}
    with st.form("profile"):
        c1, c2, c3 = st.columns(3)
        age = c1.number_input("Age", 14, 100, int(e.get("age", 30)))
        sex = c2.selectbox("Sex", calc.SEXES, index=calc.SEXES.index(e.get("sex", "Female")))
        height = c3.number_input("Height (cm)", 100.0, 250.0, float(e.get("height_cm", 165)), 0.5)
        c1, c2, c3 = st.columns(3)
        weight = c1.number_input("Current weight (kg)", 25.0, 300.0, float(e.get("weight_kg", 70)), 0.1)
        target = c2.number_input("Target weight (kg)", 25.0, 300.0, float(e.get("target_weight_kg", 65)), 0.1)
        weeks = c3.number_input("Timeline (weeks)", 1, 156, int(e.get("timeline_weeks", 20)))
        c1, c2 = st.columns(2)
        goal = c1.selectbox("Goal", calc.GOALS, index=calc.GOALS.index(e.get("goal", calc.GOALS[0])))
        levels = list(calc.ACTIVITY_LEVELS)
        act = c2.selectbox("Activity level", levels, index=levels.index(e.get("activity_level", levels[0])))
        diet = st.selectbox("Dietary preference", calc.DIETS, index=calc.DIETS.index(e.get("diet", "Vegetarian")))
        allergies = st.text_input("Allergies (comma separated)", e.get("allergies", ""), placeholder="e.g. peanuts, milk, gluten")
        conds = st.multiselect("Medical conditions", calc.CONDITIONS, default=e.get("conditions", []))
        other = st.text_input("Other conditions / medications (optional)", e.get("other_conditions", ""))
        ok = st.form_submit_button("Save profile", type="primary")
    if ok:
        p = dict(age=int(age), sex=sex, height_cm=float(height), weight_kg=float(weight),
                 target_weight_kg=float(target), timeline_weeks=int(weeks), goal=goal, activity_level=act,
                 diet=diet, allergies=allergies.strip(), conditions=conds, other_conditions=other.strip())
        errs = calc.validate_profile(p)
        if errs:
            for m in errs:
                st.error(m)
            return
        db.save_profile(p)
        st.success("Profile saved.")
        st.rerun()
    if existing:
        _, t = current_profile()
        st.subheader("Plan preview")
        show_target_warnings(t)


# ---------------------------------------------------------------- Dashboard
def progress_bar(label, value, target, unit, is_cap=False):
    pct = value / target if target else 0
    over = pct > 1
    st.markdown(f"**{label}** &nbsp; {value:.0f} / {target:.0f} {unit}" + (" &nbsp;⚠️ over" if over and is_cap else ""))
    st.progress(min(pct, 1.0))


def page_dashboard(p, t, day):
    st.title("Health dashboard")
    show_target_warnings(t)
    meals, acts, daily = db.get_meals(day), db.get_activities(day), db.get_daily(day)
    n = calc.sum_nutrition(meals)
    remaining = t.calories - n["kcal"]
    burned = sum(a["kcal"] for a in acts)
    step_kcal = calc.steps_calories(daily["steps"], p["weight_kg"])

    c = st.columns(4)
    c[0].metric("Daily target", f"{t.calories} kcal", help=f"BMR {t.bmr}, maintenance {t.tdee} kcal (Mifflin-St Jeor estimate)")
    c[1].metric("Consumed", f"{n['kcal']:.0f} kcal")
    c[2].metric("Remaining", f"{remaining:.0f} kcal", delta="over target" if remaining < 0 else None, delta_color="inverse")
    c[3].metric("Est. burned (exercise + steps)", f"{burned + step_kcal:.0f} kcal",
                help="Estimate. Targets already include your normal activity level; don't automatically eat back burned calories.")

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Nutrients vs target")
        progress_bar("Protein", n["protein"], t.protein_g, "g")
        progress_bar("Carbohydrates", n["carbs"], t.carbs_g, "g")
        progress_bar("Fat", n["fat"], t.fat_g, "g")
        progress_bar("Sugar (limit)", n["sugar"], t.sugar_g, "g", is_cap=True)
    with right:
        st.subheader("Macro split (by calories)")
        vals = [n["protein"] * 4, n["carbs"] * 4, n["fat"] * 9]
        title = "Consumed"
        if sum(vals) == 0:
            vals = [t.protein_g * 4, t.carbs_g * 4, t.fat_g * 9]
            title = "Target (nothing logged yet)"
        fig = go.Figure(go.Pie(labels=["Protein", "Carbs", "Fat"], values=vals, hole=.55,
                               marker=dict(colors=[COLORS["protein"], COLORS["carbs"], COLORS["fat"]]),
                               hovertemplate="%{label}: %{value:.0f} kcal (%{percent})<extra></extra>"))
        fig.update_layout(height=300, margin=dict(t=30, b=0, l=0, r=0), title=dict(text=title, font_size=14),
                          legend=dict(orientation="h", y=-0.05))
        st.plotly_chart(fig, width="stretch")

    st.subheader("Activity & hydration")
    c = st.columns(4)
    c[0].metric("Water", f"{daily['water_ml']} / {t.water_ml} ml")
    c[1].metric("Steps", f"{daily['steps']:,}")
    c[2].metric("Exercise", f"{sum(a['minutes'] for a in acts):.0f} min")
    c[3].metric("Exercise kcal (est.)", f"{burned:.0f}")

    st.subheader("Weight progress")
    ws = db.get_weights()
    start, cur, goal_w = ws[0]["weight_kg"], p["weight_kg"], p["target_weight_kg"]
    total = start - goal_w
    pct = max(0.0, min(1.0, (start - cur) / total)) if total else 1.0
    c = st.columns(4)
    c[0].metric("Current", f"{cur:.1f} kg")
    c[1].metric("Target", f"{goal_w:.1f} kg")
    c[2].metric("To go", f"{abs(cur - goal_w):.1f} kg")
    c[3].metric("BMI", f"{t.bmi}")
    st.progress(pct, text=f"{pct * 100:.0f}% of the way from {start:.1f} kg to {goal_w:.1f} kg")
    if t.weeks_to_target:
        st.caption(f"At the planned pace ({t.weekly_change_kg:+.2f} kg/week) you'd reach your target in about {t.weeks_to_target:.0f} weeks (estimate).")
    if len(ws) > 1:
        df = pd.DataFrame(ws)
        fig = go.Figure(go.Scatter(x=df["day"], y=df["weight_kg"], mode="lines+markers", name="Weight", line_color=COLORS["protein"]))
        fig.add_hline(y=goal_w, line_dash="dash", annotation_text="Target")
        fig.update_layout(height=280, margin=dict(t=10, b=0), yaxis_title="kg")
        st.plotly_chart(fig, width="stretch")
    else:
        st.caption("Log your weight regularly (Activity & Body page) to see a trend chart.")


# ---------------------------------------------------------------- Food logging
def page_food(p, t, day):
    st.title("Log food")
    st.caption("Nutrition values come from a small bundled reference table of **approximate** values for typical "
               "Indian preparations. Real values vary with recipe, oil and portion size - correct them manually if you know better.")
    db_foods = food_db()
    tab1, tab2, tab3, tab4 = st.tabs(["Add from food list", "Add custom food", "Today's log", "Packaged food"])
    draft = st.session_state.setdefault("draft", [])

    with tab1:
        meal_type = st.selectbox("Meal", MEAL_TYPES, key="mt")
        q = st.text_input("Search food", placeholder="roti, dal, idli, paneer...")
        opts = [f for f in db_foods if q.lower() in f["name"].lower() or q.lower() in f["category"].lower()]
        if not opts:
            st.info("No match - use 'Add custom food'.")
        else:
            f = st.selectbox("Food", opts, format_func=lambda x: f"{x['name']}  ({x['category']})")
            c1, c2 = st.columns(2)
            mode = c1.radio("Quantity in", [f"servings ({f['unit_name']} ≈ {f['unit_g']:.0f} g)", "grams"], horizontal=True)
            if mode.startswith("servings"):
                units = c2.number_input("Servings", 0.25, 20.0, 1.0, 0.25)
                grams = units * f["unit_g"]
            else:
                grams = c2.number_input("Grams", 1.0, 2000.0, f["unit_g"], 5.0)
            n = calc.scale_food(f, grams)
            st.write(f"**≈ {n['kcal']:.0f} kcal** · P {n['protein']} g · C {n['carbs']} g · F {n['fat']} g · Sugar {n['sugar']} g "
                     f"&nbsp; _(estimate for {grams:.0f} g)_")
            if not foods.diet_ok(f, p["diet"]):
                st.warning(f"This food may not match your '{p['diet']}' preference.")
            if foods.allergy_hit(f, p.get("allergies", "")):
                st.error("This food may contain an ingredient you listed as an allergy.")
            if st.button("➕ Add ingredient to meal"):
                draft.append(dict(item=f["name"], quantity_g=round(grams, 1), **n))
                st.rerun()
        if draft:
            st.markdown("**Meal being built**")
            st.dataframe(pd.DataFrame(draft), hide_index=True, width="stretch")
            c1, c2, _ = st.columns([1, 1, 3])
            if c1.button("✅ Save meal to log", type="primary"):
                for d in draft:
                    db.add_meal(day, meal_type, d["item"], d["quantity_g"], d)
                st.session_state.draft = []
                st.success("Meal logged.")
                st.rerun()
            if c2.button("Clear"):
                st.session_state.draft = []
                st.rerun()

    with tab2:
        with st.form("custom", clear_on_submit=True):
            mt = st.selectbox("Meal", MEAL_TYPES, key="mt2")
            name = st.text_input("Food / dish name")
            grams = st.number_input("Quantity (g, optional)", 0.0, 3000.0, 0.0, 10.0)
            c = st.columns(5)
            kcal = c[0].number_input("kcal", 0.0, 5000.0, 0.0, 10.0)
            pr = c[1].number_input("Protein g", 0.0, 300.0, 0.0, 1.0)
            cb = c[2].number_input("Carbs g", 0.0, 600.0, 0.0, 1.0)
            ft = c[3].number_input("Fat g", 0.0, 300.0, 0.0, 1.0)
            sg = c[4].number_input("Sugar g", 0.0, 300.0, 0.0, 1.0)
            ok = st.form_submit_button("Add (values are totals for the quantity)")
        if ok:
            if not name.strip():
                st.error("Please enter a name.")
            elif kcal <= 0:
                st.error("Calories must be greater than 0.")
            else:
                db.add_meal(day, mt, name.strip(), grams or None, dict(kcal=kcal, protein=pr, carbs=cb, fat=ft, sugar=sg), "manual entry")
                st.success("Added.")
                st.rerun()

    with tab4:
        packaged_tab()

    with tab3:
        meals = db.get_meals(day)
        if not meals:
            st.info("Nothing logged for this day.")
        else:
            df = pd.DataFrame(meals)
            df["delete"] = False
            cols = ["meal_type", "item", "quantity_g", "kcal", "protein", "carbs", "fat", "sugar", "source"]
            edited = st.data_editor(
                df[["id", *cols, "delete"]], hide_index=True, width="stretch", key=f"ed{day}",
                disabled=["id", "meal_type", "source"], column_config={"id": None})
            st.caption("Edit any value to correct it (marked 'manually corrected'), or tick delete.")
            if st.button("Save changes"):
                for _, r in edited.iterrows():
                    orig = df[df.id == r.id].iloc[0]
                    if r["delete"]:
                        db.delete_meal(int(r.id))
                    elif any(r[c] != orig[c] and not (pd.isna(r[c]) and pd.isna(orig[c])) for c in cols[1:8]):
                        if not str(r["item"]).strip() or any((r[c] or 0) < 0 for c in cols[3:8]):
                            st.error("Names can't be empty and values can't be negative.")
                            return
                        db.update_meal(int(r.id), **{c: (None if pd.isna(r[c]) else r[c]) for c in cols[1:8]})
                st.rerun()


# ---------------------------------------------------------------- Packaged foods
def packaged_tab():
    st.caption("Search Open Food Facts (free, crowd-sourced label data) by product name or barcode, or type the values from the "
               "nutrition label. Saved products appear in **Add from food list** (search by name). Always check against your pack.")
    q = st.text_input("Product name or barcode", placeholder="e.g. parle-g, maggi masala, 8901058852257")
    if st.button("🔍 Search Open Food Facts") and q.strip():
        try:
            with st.spinner("Searching..."):
                st.session_state.pk_results = packaged.search(q)
            if not st.session_state.pk_results:
                st.info("No products with calorie data found. Try another spelling, or enter the label values below.")
        except packaged.PackagedUnavailable as e:
            st.session_state.pk_results = []
            st.error(str(e))
    res = st.session_state.get("pk_results") or []
    if res:
        f = st.selectbox("Results", res, format_func=lambda x: f"{x['name']} - {x['kcal']:.0f} kcal/100 g")
        st.write(f"Per 100 g: **{f['kcal']:.0f} kcal** · P {f['protein']} g · C {f['carbs']} g · F {f['fat']} g · Sugar {f['sugar']} g "
                 f"&nbsp; (serving: {f['unit_name']} ≈ {f['unit_g']:.0f} g)")
        if f["diet"] == "unknown":
            st.caption("Vegetarian/vegan status unknown for this product - check the pack.")
        if f["allergens"]:
            st.caption("Allergens listed: " + ", ".join(f["allergens"]))
        if st.button("💾 Save to my foods"):
            db.save_custom_food(f)
            food_db.clear()
            st.success("Saved. Find it under Log food → Add from food list.")
    with st.expander("Or enter from the nutrition label"):
        with st.form("label", clear_on_submit=True):
            name = st.text_input("Product name (with brand)")
            c = st.columns(5)
            kcal = c[0].number_input("kcal /100 g", 0.0, 900.0, 0.0, 10.0)
            pr = c[1].number_input("Protein g", 0.0, 100.0, 0.0, 0.5)
            cb = c[2].number_input("Carbs g", 0.0, 100.0, 0.0, 0.5)
            ft = c[3].number_input("Fat g", 0.0, 100.0, 0.0, 0.5)
            sg = c[4].number_input("Sugar g", 0.0, 100.0, 0.0, 0.5)
            c = st.columns(3)
            serv = c[0].number_input("Serving size (g)", 1.0, 1000.0, 30.0, 5.0)
            diet = c[1].selectbox("Diet type", ["vegetarian", "vegan", "nonveg"])
            allerg = c[2].text_input("Allergens (comma separated)")
            if st.form_submit_button("Save product (values per 100 g)"):
                if not name.strip() or kcal <= 0:
                    st.error("Enter a name and calories per 100 g.")
                elif pr + cb + ft > 100:
                    st.error("Protein + carbs + fat can't exceed 100 g per 100 g.")
                else:
                    al = [x.strip().lower() for x in allerg.split(",") if x.strip()]
                    db.save_custom_food(dict(name=name.strip(), category="Packaged (my label entry)", source="entered from pack label",
                                             kcal=kcal, protein=pr, carbs=cb, fat=ft, sugar=sg, unit_name=f"1 serving ({serv:.0f} g)",
                                             unit_g=serv, diet=diet, dairy="milk" in al or "dairy" in al, allergens=al))
                    food_db.clear()
                    st.success("Saved.")


# ---------------------------------------------------------------- Activity & body
def page_activity(p, t, day):
    st.title("Activity & body")
    daily = db.get_daily(day)
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Water & steps")
        w = st.number_input("Water today (ml)", 0, 10000, int(daily["water_ml"]), 250)
        s = st.number_input("Steps today", 0, 100000, int(daily["steps"]), 500)
        c = st.columns(2)
        if c[0].button("Save water & steps"):
            db.set_daily(day, w, s)
            st.success("Saved.")
            st.rerun()
        if c[1].button("+250 ml water"):
            db.set_daily(day, daily["water_ml"] + 250)
            st.rerun()
        st.caption(f"Step calories are a rough estimate (~{calc.steps_calories(1000, p['weight_kg']):.0f} kcal per 1,000 steps). "
                   "Walking logged below may overlap with steps.")
    with c2:
        st.subheader("Log weight")
        kg = st.number_input("Weight (kg)", 25.0, 300.0, float(p["weight_kg"]), 0.1)
        if st.button("Save weight"):
            db.log_weight(day, kg)
            st.success("Saved.")
            st.rerun()

    st.subheader("Log exercise")
    with st.form("act", clear_on_submit=True):
        c = st.columns(3)
        name = c[0].selectbox("Activity", list(calc.ACTIVITY_METS))
        mins = c[1].number_input("Minutes", 1, 600, 30, 5)
        override = c[2].number_input("Override kcal (optional)", 0.0, 3000.0, 0.0, 10.0)
        ok = st.form_submit_button("Add activity")
    if ok:
        if override > 0:
            db.add_activity(day, name, mins, override, "manual entry")
        else:
            db.add_activity(day, name, mins, round(calc.activity_calories(name, p["weight_kg"], mins)))
        st.rerun()
    acts = db.get_activities(day)
    for a in acts:
        c = st.columns([4, 2, 2, 1])
        c[0].write(a["name"])
        c[1].write(f"{a['minutes']:.0f} min")
        c[2].write(f"≈ {a['kcal']:.0f} kcal ({a['source']})")
        if c[3].button("🗑", key=f"da{a['id']}"):
            db.delete_activity(a["id"])
            st.rerun()
    if not acts:
        st.info("No exercise logged for this day.")
    st.caption("Calories burned are MET-based estimates. Stop any exercise that causes pain, dizziness or chest discomfort.")


# ---------------------------------------------------------------- AI coach
def render_meals(data, profile):
    show_disclaimer()  # shown before every personalised recommendation
    for w in ai.allergy_warnings(data, profile.get("allergies", "")):
        st.error("⚠️ " + w)
    for i, m in enumerate(data["meals"]):
        nut = m.get("estimated_nutrition", {})
        with st.expander(f"{m.get('meal_type', '')} · {m.get('name', 'Meal')} — ≈{nut.get('kcal', '?')} kcal", expanded=i == 0):
            if m.get("why"):
                st.write(m["why"])
            st.markdown("**Ingredients**")
            for ing in m.get("ingredients", []):
                st.write(f"- {ing.get('item')} — {ing.get('quantity')}")
            st.markdown("**Steps**")
            for j, step in enumerate(m.get("steps", []), 1):
                st.write(f"{j}. {step}")
            st.caption(f"AI estimate (not exact): {nut.get('kcal', '?')} kcal · P {nut.get('protein_g', '?')} g · "
                       f"C {nut.get('carbs_g', '?')} g · F {nut.get('fat_g', '?')} g · Sugar {nut.get('sugar_g', '?')} g")
            if st.button("Log this meal (as AI estimate)", key=f"log{st.session_state.get('ai_n', 0)}_{i}"):
                try:
                    vals = dict(kcal=float(nut["kcal"]), protein=float(nut.get("protein_g", 0)), carbs=float(nut.get("carbs_g", 0)),
                                fat=float(nut.get("fat_g", 0)), sugar=float(nut.get("sugar_g", 0)))
                    mt = m.get("meal_type") if m.get("meal_type") in MEAL_TYPES else "Snack"
                    db.add_meal(st.session_state.day, mt, m.get("name", "AI meal"), None, vals, "AI estimate")
                    st.success("Logged - you can correct the numbers in Log food → Today's log.")
                except (KeyError, TypeError, ValueError):
                    st.error("The AI didn't give usable numbers for this meal; add it manually instead.")
    if data.get("notes"):
        st.info(data["notes"])


def page_ai(p, t, day):
    st.title("AI meal coach")
    show_disclaimer()
    if t.refer_professional:
        st.error("Your medical profile is complex. AI suggestions are general ideas only - please follow your doctor/dietitian's advice.")
    n = calc.sum_nutrition(db.get_meals(day))
    rem = {"kcal": max(0, t.calories - n["kcal"]), "protein": max(0, t.protein_g - n["protein"]),
           "carbs": max(0, t.carbs_g - n["carbs"]), "fat": max(0, t.fat_g - n["fat"]), "sugar": max(0, t.sugar_g - n["sugar"])}
    st.caption(f"Remaining today: **{rem['kcal']:.0f} kcal** · protein {rem['protein']:.0f} g · carbs {rem['carbs']:.0f} g · "
               f"fat {rem['fat']:.0f} g · sugar {rem['sugar']:.0f} g")

    def run(mode, extra=None):
        try:
            with st.spinner("Retrieving your history and asking DeepSeek..."):
                task_text = " ".join(str(v) for v in (extra or {}).values()) or mode.replace("_", " ")
                ctx = rag.get_context(p, t, rem, task_text)
                st.session_state.ai_context = ctx
                st.session_state.ai_result = ai.recommend(mode, p, t, rem, extra, ctx)
            st.session_state.ai_n = st.session_state.get("ai_n", 0) + 1
        except ai.AIUnavailable as e:
            st.session_state.ai_result = None
            st.error(f"{e} Manual logging and the dashboard still work.")

    tab1, tab2, tab3 = st.tabs(["Make my next meal", "Plan my day", "Substitute"])
    with tab1:
        mt = st.selectbox("Which meal?", ["Any / next meal", *MEAL_TYPES])
        if st.button("🍽️ Make My Next Meal", type="primary"):
            run("next_meal", {"meal_type": mt})
    with tab2:
        if st.button("📅 Plan my whole day"):
            eaten = ", ".join(m["item"] for m in db.get_meals(day))
            run("daily_plan", {"eaten": eaten})
    with tab3:
        orig = st.text_input("Meal or ingredient to replace", placeholder="e.g. paneer butter masala")
        why = st.text_input("Reason (optional)", placeholder="don't like it / out of stock / allergy")
        if st.button("🔄 Suggest substitutes"):
            if orig.strip():
                run("substitute", {"original": orig.strip(), "reason": why})
            else:
                st.error("Enter what you'd like to replace.")
    if st.session_state.get("ai_result"):
        st.divider()
        render_meals(st.session_state.ai_result, p)
        ctx = st.session_state.get("ai_context") or {}
        with st.expander("What the coach retrieved about you (RAG)"):
            if ctx.get("error"):
                st.warning(f"Personal memory was unavailable, so this answer used only your profile. ({ctx['error']})")
            for m in ctx.get("memory", []):
                st.write(f"- **{m['kind']}**: {m['text']}")
            if ctx.get("foods"):
                st.caption("Reference foods supplied to the AI: " + "; ".join(x.split(" (")[0] for x in ctx["foods"]))
            if not ctx.get("memory") and not ctx.get("error"):
                st.caption("Nothing relevant yet - add notes and log meals to personalise suggestions.")


# ---------------------------------------------------------------- notes
NOTE_KINDS = ["Preference", "Dislike", "Routine", "Doctor / dietitian advice", "Other"]


def page_notes():
    st.title("My notes")
    st.caption("Anything specific to you. These are stored in a local vector database and retrieved by the AI Meal Coach "
               "(e.g. \"I dislike bhindi\", \"gym at 6 pm, need a snack before\", \"doctor advised less salt\"). "
               "Notes never override your diet, allergy or medical limits.")
    with st.form("note", clear_on_submit=True):
        kind = st.selectbox("Type", NOTE_KINDS)
        text = st.text_area("Note", max_chars=500)
        if st.form_submit_button("Add note"):
            if text.strip():
                db.add_note(kind, text)
                st.rerun()
            else:
                st.error("Write something first.")
    for n in db.get_notes():
        c = st.columns([8, 1])
        c[0].write(f"**{n['kind']}** - {n['text']}")
        if c[1].button("🗑", key=f"dn{n['id']}"):
            db.delete_note(n["id"])
            st.rerun()
    st.caption("Your meal and exercise history is also indexed automatically.")


# ---------------------------------------------------------------- main
def main():
    existing = db.get_profile()
    if not existing:
        page_profile(None)
        return
    p, t = current_profile()
    st.sidebar.title("🥗 AI Health Coach")
    page = st.sidebar.radio("Navigate", ["Dashboard", "Log food", "Activity & body", "AI meal coach", "My notes", "Profile"], label_visibility="collapsed")
    day = st.sidebar.date_input("Date", date.today(), max_value=date.today()).isoformat()
    st.session_state.day = day
    st.sidebar.caption("Data is stored locally in data/health.db")
    {"Dashboard": page_dashboard, "Log food": page_food, "Activity & body": page_activity,
     "AI meal coach": page_ai, "My notes": lambda *a: page_notes()}.get(page, lambda *a: page_profile(existing))(p, t, day)


main()

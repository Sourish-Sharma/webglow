import json
import os

MASTER_PROMPT_TEMPLATE = """You are an Expert Frontend Web Developer and UI/UX Designer.
Your task is to generate a complete, responsive restaurant website using HTML5, CSS3, and Vanilla JavaScript.
Do NOT output generic templates. If any provided data point is vague or "unknown", aggressively infer a strong, highly opinionated interpretation based on the cuisine and price tier.

=========================================
1. THE BRAND BLUEPRINT (POSITIONING)
=========================================
Restaurant Name: {name}
Primary Hook (CORE FOCUS): "{primary_strength}"
Target Audience: {audience}
Ideal Occasions: {occasions}

=========================================
2. UI/UX ARCHITECTURE & DESIGN SYSTEM
=========================================
Brand Tone: {tone}
Atmosphere & Vibe: {vibes}

Price Tier UI Directives ({price}):
{price_logic}

Strict Layout & Styling Rules:
- FRAMEWORK: Use Tailwind CSS via CDN for 95% of all styling.
- CUSTOM CSS: Use `styles.css` ONLY for custom keyframe animations, smooth scrolling, or `@font-face` font imports. Do NOT recreate layout styles in CSS.
- RESPONSIVENESS: Mobile-first is mandatory. Use modern CSS Grid/Flexbox.
- CONTAINERS: Constrain main content wrappers using `max-w-7xl mx-auto`. Ensure ample section pacing (`py-16` to `py-24`).
- ANIMATION: Add subtle, high-end interactions (hover states, smooth transitions, fade-ins). Do not over-animate.

=========================================
3. COMPONENT SPECIFICATIONS
=========================================
A. NAVIGATION & HERO
- Navigation: Include a sticky navbar with a functioning mobile hamburger menu (use `script.js` for the toggle logic).
- Hero: Do NOT use generic "Welcome to..." text. The headline must be a specific emotional hook targeting [{audience}] looking for [{occasions}]. Anchor the hero visually around the Primary Hook: "{primary_strength}".
- Call to Action (CTA): Include at least one highly visible CTA (e.g., "Book a Table", "Order Online") in both the nav and hero.

B. THE VALUE PROPOSITION (ABOUT / VIBE)
- Keep visual clutter low. Focus strictly on these core business strengths:
{secondary_strengths}

C. SIGNATURE MENU
- Cuisine Focus: {cuisines}
- Highlight these specific dishes using premium UI card/list treatments:
{good_dishes}

D. FOOTER & METADATA
- Phone: {phone} | Address: {address} | Parking: {parking}

=========================================
4. LOCAL ASSETS & IMAGE ROUTING
=========================================
- Do NOT use external image URLs. Assume all images are stored locally in an `./images/` directory.
- Use highly semantic filenames (e.g., `<img src="./images/hero-background.jpg" alt="...">`).

=========================================
5. TECHNICAL REQUIREMENTS & CONSTRAINTS
=========================================
- EXCLUSIONS: Do NOT include, render, or mention these items anywhere: {bad_dishes}.
- HTML REQUIREMENTS: Your HTML MUST include these exact asset links in the head/body:
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="styles.css">
  <script src="script.js" defer></script>
- SCOPE: Output complete, production-ready code. Do not use placeholder text (like "Lorem Ipsum"). Generate highly relevant, semantic copy based on the provided brand identity.
"""

INPUT_JSONL = "enriched_restaurants.jsonl"
OUTPUT_DIR = "deepseek_prompts"

def compile_prompts():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    with open(INPUT_JSONL, "r", encoding="utf-8") as file:
        for idx, line in enumerate(file):
            if not line.strip():
                continue

            data = json.loads(line.strip())

            identity = data.get("brand_identity", {})
            audience = data.get("audience_profile", {})
            value = data.get("value_proposition", {})
            menu = data.get("menu_highlights", {})
            ops = data.get("operational_metadata", {})

            price_tier = identity.get("price_tier", "").lower()
            if "premium" in price_tier:
                price_logic = "- LAYOUT: Minimalist and spacious. Use generous padding (e.g., py-24, gap-16).\n- TYPOGRAPHY: Elegant serif headings (font-serif) or sleek, thin sans-serifs. Use wide tracking (tracking-wide).\n- PALETTE: Deep, muted base (stone-900, slate-900) with subtle metallic or high-contrast monochromatic accents."
            elif "affordable" in price_tier:
                price_logic = "- LAYOUT: Dense, vibrant, and energetic. Pack information efficiently with clear calls-to-action.\n- TYPOGRAPHY: Bold, chunky sans-serif headings (font-black, tracking-tight).\n- PALETTE: Warm, appetite-inducing colors (reds, oranges, warm yellows) with high-contrast text."
            else:
                price_logic = "- LAYOUT: Balanced and accessible. Comfortable padding (e.g., py-16, gap-8).\n- TYPOGRAPHY: Clean, modern sans-serif fonts.\n- PALETTE: Warm, inviting, and cozy tones that reflect the cuisine's natural ingredients."

            strengths_list = value.get("top_strengths", [])

            primary_strength = strengths_list[0] if strengths_list else "A unique and memorable dining experience"

            secondary_strengths_list = strengths_list[1:4] if len(strengths_list) > 1 else []
            secondary_strengths = "\n".join([f"  * {s}" for s in secondary_strengths_list]) if secondary_strengths_list else "  * Exceptional service and atmosphere."

            bad_dishes_list = menu.get("dishes_to_avoid_featuring", [])
            bad_dishes_str = ", ".join(bad_dishes_list) if bad_dishes_list else "None"

            good_dishes = "\n".join([f"  * {d}" for d in menu.get("highly_rated_dishes", [])]) if menu.get("highly_rated_dishes") else "  * Chef's Specials"

            final_prompt = MASTER_PROMPT_TEMPLATE.format(
                name=identity.get("clean_name", "Restaurant"),
                primary_strength=primary_strength,
                audience=", ".join(audience.get("target_segments", ["diners"])),
                occasions=", ".join(audience.get("occasion_types", ["dining"])),
                tone=identity.get("brand_tone", "neutral"),
                vibes=", ".join(identity.get("ambience_vibes", ["pleasant"])),
                price=identity.get("price_tier", "Unknown"),
                price_logic=price_logic,
                secondary_strengths=secondary_strengths,
                cuisines=", ".join(identity.get("cuisine_tags", ["International"])),
                good_dishes=good_dishes,
                phone=ops.get("contact_phone", "Unknown"),
                address=ops.get("full_address", "Unknown"),
                parking=ops.get("has_parking", "unknown"),
                bad_dishes=bad_dishes_str
            )

            safe_name = identity.get('clean_name', f'restaurant_{idx}').replace(" ", "_").lower()
            output_file = os.path.join(OUTPUT_DIR, f"{safe_name}_prompt.txt")

            with open(output_file, "w", encoding="utf-8") as out_f:
                out_f.write(final_prompt)

            print(f"Successfully compiled structured output prompt for: {identity.get('clean_name')}")

if __name__ == "__main__":
    compile_prompts()
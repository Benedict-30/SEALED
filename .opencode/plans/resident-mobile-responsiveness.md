# Resident UI — Flexible on Any Device (Implementation Plan)

Scope: make the resident experience (dashboard → request → track → history → profile → notifications) plus the public/auth pages residents and visitors use (home, services, about, login, register, verify, password reset) layout-fluid across phones (320px+), tablets, and desktops.

No backend logic, models, data, or migration changes. All changes are CSS, template markup, and 2 JS helper tweaks.

## Verification gate (run after every phase from `my_project/`)
- `python manage.py check`
- `python smoke_tests.py`
- Manual: `python manage.py runserver`, DevTools responsive at 320 / 375 / 768 / 1024, walk the resident flow + auth/public pages.

---

## Phase 1 — Resident app pages

### 1.1 Request/preview modal UX on phones — `brgy/static/js/resident/request_document.js`
- `openModal()` (~line 14): add `document.body.style.overflow = 'hidden';` (mirrors `openPreview()` line 203).
- `closeModal()` (~line 29): replace direct unlock with a `syncBodyScroll()` call.
- Add helper:
  ```js
  function syncBodyScroll() {
      const reqActive = document.getElementById('reqModal').classList.contains('active');
      const previewActive = document.getElementById('previewModal').classList.contains('active');
      document.body.style.overflow = (reqActive || previewActive) ? 'hidden' : '';
  }
  ```
- Change `closePreview()` (line 222) to use `syncBodyScroll()` instead of `document.body.style.overflow = '';` (keeps lock if the request modal is still open).
- Add backdrop-tap close (after the Escape handlers, ~line 168 and ~line 249):
  ```js
  document.getElementById('reqModal').addEventListener('click', function (e) {
      if (e.target === this) closeModal();
  });
  document.getElementById('previewModal').addEventListener('click', function (e) {
      if (e.target === this) closePreview();
  });
  ```

### 1.2 Top bar safe-area (notch phones) — `brgy/static/css/global/topbar.css`
`base.html:6` already sets `viewport-fit=cover`. Update `.topbar` (lines 5–19):
```css
height: calc(var(--topbar-height) + env(safe-area-inset-top, 0px));
padding-top: env(safe-area-inset-top, 0px);
background-clip: padding-box; /* keep blur/border under control */
```
(`*box-sizing: border-box` is global, so content stays centered in the original 64px area below the notch.)

### 1.3 Profile sticky save-bar alignment — `brgy/static/css/resident/profile.css`
- `.save-bar-enhanced` (lines 1283–1287): change `left: var(--sidebar-width, 280px);` → `left: 0;`. The sidebar is always off-canvas (`sidebar.css:17`), so the 260–280px offset no longer matches anything.
- Delete the now-redundant `left: 0;` override inside `@media (max-width: 768px)` (line ~1438).

### 1.4 Track-request progress ring on ≤480px
The global `@media (max-width: 480px)` rule in `dashboard.css` (`.progress-ring-wrapper`/`.progress-ring`/`.progress-text` → 104/104/72px, block display) already applies to `track_request.html:32-47` because it uses the same wrapper/text classes. After implementation:
- Verify it renders concentric on the track page (DevTools 375px).
- If it looks off, add a scoped override in `brgy/static/css/resident/track_request.css`:
  ```css
  @media (max-width: 480px) {
      .progress-ring-wrapper.track-ring,
      .progress-ring-wrapper.track-ring .progress-ring {
          width: 104px;
          height: 104px;
      }
  }
  ```

---

## Phase 2 — Public pages (home / services / verify / register)

### 2.1 Verify page responsive — `brgy/static/css/public/verify.css` (currently zero media queries)
Append:
```css
@media (max-width: 640px) {
    .verify-container { padding: 12px; }
    .verify-card { padding: 28px 18px; border-radius: 18px; }
    .verify-icon { width: 72px; height: 72px; font-size: 32px; }
    .verify-card h2 { font-size: 22px; }
    .verify-form input { font-size: 18px; letter-spacing: 3px; padding: 15px 12px; }
    .verify-details { padding: 18px 14px; }
    .verify-detail-row .value { word-break: break-word; }
}
@media (max-width: 380px) {
    .verify-card { padding: 22px 14px; }
    .verify-detail-row { flex-direction: column; align-items: flex-start; gap: 2px; }
    .verify-detail-row .value { text-align: left; }
}
```
Optional in `verify.html:49`: drop the inline `monospace/letter-spacing` in favor of a `.verify-code` class (add `word-break: break-all`) so a long code never overflows.

### 2.2 Services grid clip at 320px — `brgy/static/css/public/pages.css:88-92`
```css
grid-template-columns: repeat(auto-fill, minmax(min(100%, 300px), 1fr));
```
(Container is 280px wide at 320px viewport; the 300px min track was clipping.)

### 2.3 Home page — `brgy/static/css/public/home.css`
Add a `≤480px` block after the existing `@media (max-width: 768px)` (ends line 794):
```css
@media (max-width: 480px) {
    .landing-hero-content h1 { font-size: 30px; letter-spacing: -0.5px; }
    .landing-features, .landing-steps, .landing-cta { padding: 56px 12px; }
    .landing-features-header h2, .landing-steps-header h2, .landing-cta h2 { font-size: 24px; }
    .feature-card { padding: 26px 20px; }
    .features-grid, .steps-grid { grid-template-columns: 1fr; }
    .step-card p { max-width: none; }
    .landing-cta { padding: 64px 16px; }
}
```
De-inline the landing-verify section (`home.html:137-152`): replace inline styles with classes and add to `home.css`:
```css
.landing-verify { padding: 80px 20px; background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); color: #fff; text-align: center; }
.landing-verify .reveal { max-width: 650px; margin: 0 auto; }
.landing-verify-icon { width: 70px; height: 70px; background: var(--primary); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 24px; font-size: 28px; box-shadow: 0 10px 20px rgba(0,0,0,0.3); }
.landing-verify h2 { font-size: 32px; font-weight: 800; margin-bottom: 12px; }
.landing-verify p { font-size: 16px; opacity: 0.8; margin-bottom: 32px; }
@media (max-width: 480px) {
    .landing-verify { padding: 56px 16px; }
    .landing-verify-icon { width: 56px; height: 56px; font-size: 24px; }
    .landing-verify h2 { font-size: 26px; }
    .landing-verify p { font-size: 14.5px; }
    .landing-verify a.btn-landing-primary { padding: 14px 20px; }
}
```

### 2.4 Register selfie row — `brgy/templates/brgy/register.html:229-230` + `brgy/static/css/public/register.css`
- Replace the inline `style="display:flex; gap:10px; align-items:center;"` with a `class="selfie-row"` (keep `flex:1` on the label as a class so it survives the stack).
- Add to `register.css`:
  ```css
  .selfie-row { display: flex; gap: 10px; align-items: center; }
  .selfie-row .custom-file-upload { flex: 1; }
  ```
- In `@media (max-width: 480px)` block:
  ```css
  .selfie-row { flex-direction: column; align-items: stretch; }
  .selfie-row .btn-camera { width: 100%; }
  ```

---

## Phase 3 — Small-screen hardening & polish

### 3.1 Auth input icon classes — `login.html:55-64`, `password_reset.html:53-55`, `password_reset_confirm.html`
Replace the three inline styles (`.password-wrap` icon `left:14px`, input `padding-left:38px`) with classes in `brgy/static/css/global/auth.css`:
```css
.input-icon { position: absolute; left: 14px; top: 50%; transform: translateY(-50%); color: var(--text-muted); font-size: 13px; pointer-events: none; }
.input-with-icon { padding-left: 38px !important; }
@media (max-width: 380px) {
    .input-icon { left: 12px; }
    .input-with-icon { padding-left: 34px !important; }
}
```
`.password-wrap` is already `position: relative` (auth.css), so the wrapper inline `position:relative` can be dropped.

### 3.2 Badge/button nowrap on very narrow screens — `brgy/static/css/global/components.css`
Append to the existing `@media (max-width: 768px)` mobile block:
```css
.badge, .btn { white-space: normal; }
```
Guards labels like "Ready for Pickup" and long CTA text on ≤320px.

### 3.3 Dark/light theme pre-paint on all pages (FOUC)
- Extract the theme *startup* logic (root attribute from `localStorage`/`prefers-color-scheme`) currently in `brgy/static/js/global/script.js` section 9 (lines 244–285, `storedTheme` + `applyTheme(root)` + system-query listener) into a new head-loaded file `brgy/static/js/global/theme-init.js`.
- Keep the `#themeToggle` click handler in `script.js`.
- Load `theme-init.js` in the `<head>` of:
  - `brgy/templates/brgy/base.html` (after `theme.js`, line 12)
  - `brgy/templates/brgy/base_auth.html` (after the stylesheet links, line 11)
  - `brgy/templates/brgy/home.html`, `services.html`, `about.html` (add `<head>` block; these extend a standalone base — confirm the base used by adding to their head or shared partial)
- Net effect: no light-theme flash on reload on auth/public pages.

---

## Files touched (summary)
- `brgy/static/js/resident/request_document.js` — body scroll lock + overlay close (#1.1)
- `brgy/static/css/global/topbar.css` — safe-area-top (#1.2)
- `brgy/static/css/resident/profile.css` — save-bar `left:0` (#1.3)
- `brgy/static/css/resident/track_request.css` — scoped ring (only if needed, #1.4)
- `brgy/static/css/public/verify.css` (+ optional `verify.html`) — responsive (#2.1)
- `brgy/static/css/public/pages.css` — services grid (#2.2)
- `brgy/static/css/public/home.css` + `brgy/templates/brgy/home.html` — mobile block + de-inline landing-verify (#2.3)
- `brgy/templates/brgy/register.html` + `brgy/static/css/public/register.css` — selfie row (#2.4)
- `login.html` / `password_reset.html` / `password_reset_confirm.html` + `auth.css` — icon inputs (#3.1)
- `components.css` — nowrap guard (#3.2)
- new `brgy/static/js/global/theme-init.js` + heads of `base.html` / `base_auth.html` / public pages (#3.3)
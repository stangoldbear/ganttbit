/* ============================================================================
   GanttBit: the colours, before the first paint.

   Loaded blocking in <head> and after both stylesheets, so it can read what
   they computed and write over it. It does two jobs, and they are the same
   job: put on screen the colours that have to be right before anything
   renders, or the page flashes the wrong ones on every navigation.

   1. The theme, which is one attribute on <html>.
   2. The two ends of the priority ramp.

   The ramp is worked out here rather than generated into themes.css because
   it depends on three things a stylesheet cannot combine: the colour the user
   picked, the surface of whichever theme is on, and a target contrast. What
   reaches the rows is one custom property each, `--band` and `--band-end`,
   and every row says only how far along it sits.
   ========================================================================== */
(function () {
  'use strict';

  var THEME_KEY = 'dah_theme';
  var BAND_KEY = 'dah_band';

  /* Indigo, halfway saturated, fading to a near-grey that still reads. Red is
     deliberately not the default: `--destructive` means blocked, and a rank is
     not an alarm. */
  var BAND_DEFAULTS = { hue: 223, sat: 53, fade: 16, tint: 30 };

  /* The band is held at this contrast against the card it sits on, whatever
     theme is underneath. Solving for it, instead of picking a lightness, is
     what keeps 25 palettes behaving the same. */
  var HOT_CONTRAST = 4.0;
  var COLD_SAT = 7;               // the cold end is a grey, not a pale accent

  function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
  }

  function readBand() {
    var band = {
      hue: BAND_DEFAULTS.hue, sat: BAND_DEFAULTS.sat,
      fade: BAND_DEFAULTS.fade, tint: BAND_DEFAULTS.tint
    };
    try {
      var stored = JSON.parse(localStorage.getItem(BAND_KEY) || 'null');
      if (stored) {
        if (isFinite(stored.hue)) band.hue = clamp(+stored.hue, 0, 359);
        if (isFinite(stored.sat)) band.sat = clamp(+stored.sat, 0, 95);
        if (isFinite(stored.fade)) band.fade = clamp(+stored.fade, 12, 45);
        if (isFinite(stored.tint)) band.tint = clamp(+stored.tint, 0, 40);
      }
    } catch (err) { /* defaults */ }
    return band;
  }

  /* ─── Colour ───────────────────────────────────────────────────────────────
     HSL in, relative luminance out, by the WCAG definition, enough to solve
     for a contrast ratio and nothing more. */
  function hslToRgb(hue, sat, light) {
    sat /= 100; light /= 100;
    var c = (1 - Math.abs(2 * light - 1)) * sat;
    var x = c * (1 - Math.abs(((hue / 60) % 2) - 1));
    var m = light - c / 2;
    var seg = [[c,x,0],[x,c,0],[0,c,x],[0,x,c],[x,0,c],[c,0,x]][Math.floor(hue / 60) % 6];
    return [seg[0] + m, seg[1] + m, seg[2] + m];
  }

  function luminance(rgb) {
    var channel = function (value) {
      return value <= 0.04045 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2]);
  }

  function contrast(a, b) {
    var x = luminance(a), y = luminance(b);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
  }

  /* The lightness at which this hue reaches `target` against the surface.
     Swept rather than solved: the curve is not monotonic once the surface sits
     mid-scale, and 80 steps of integer lightness is what the input offers
     anyway. */
  function solve(hue, sat, surface, target) {
    var best = 50, gap = Infinity;
    for (var light = 12; light <= 92; light++) {
      var distance = Math.abs(contrast(hslToRgb(hue, sat, light), surface) - target);
      if (distance < gap) { gap = distance; best = light; }
    }
    return best;
  }

  /* `--card` is `H S% L%`, the shape every theme token has, so that
     `hsl(var(--card) / .5)` works everywhere. */
  function surfaceOf(root) {
    var raw = getComputedStyle(root).getPropertyValue('--card').trim().split(/[\s/]+/);
    var hue = parseFloat(raw[0]), sat = parseFloat(raw[1]), light = parseFloat(raw[2]);
    if (!isFinite(hue) || !isFinite(sat) || !isFinite(light)) return [1, 1, 1];
    return hslToRgb(hue, sat, light);
  }

  function applyBand(band) {
    var root = document.documentElement;
    band = band || readBand();
    var surface = surfaceOf(root);
    var hot = solve(band.hue, band.sat, surface, HOT_CONTRAST);
    var cold = solve(band.hue, COLD_SAT, surface, band.fade / 10);

    root.style.setProperty('--band', band.hue + ' ' + band.sat + '% ' + hot + '%');
    root.style.setProperty('--band-end', band.hue + ' ' + COLD_SAT + '% ' + cold + '%');
    root.style.setProperty('--band-tint', band.tint + '%');
  }

  function applyTheme() {
    try {
      var theme = localStorage.getItem(THEME_KEY);
      // Any key themes.css declares; the pattern is the whole validation there
      // is to do, since an unknown one simply matches no block.
      if (theme && /^[a-z0-9-]{1,40}$/.test(theme) && theme !== 'system') {
        document.documentElement.setAttribute('data-theme', theme);
      }
    } catch (err) {
      /* No storage: the system preference decides, which is the default anyway. */
    }
  }

  applyTheme();
  applyBand();

  /* app.js re-runs this when the theme changes or a slider moves: the surface
     it solves against has moved, so the answer has to be worked out again. */
  window.dahBand = { apply: applyBand, read: readBand, defaults: BAND_DEFAULTS, key: BAND_KEY };
})();

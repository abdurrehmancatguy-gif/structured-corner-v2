/* BGS Corner — front-end only. No backend, no persistence beyond this tab. */
(function () {
  "use strict";
  var aed = function (n) {
    return "AED " + n.toLocaleString("en-AE", { minimumFractionDigits: n % 1 ? 2 : 0,
                                                maximumFractionDigits: 2 });
  };

  /* ---------- quantity steppers ---------- */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-step]");
    if (!btn) return;
    e.preventDefault();
    var box = btn.closest("[data-stepper]");
    var out = box.querySelector("[data-qty]");
    var next = Math.max(1, Math.min(20, parseInt(out.textContent, 10) + parseInt(btn.dataset.step, 10)));
    out.textContent = next;
    box.querySelector('[data-step="-1"]').disabled = next <= 1;
    recalc();
  });

  /* ---------- cart totals ---------- */
  function recalc() {
    var lines = document.querySelectorAll("[data-line]");
    if (!lines.length) return;
    var subtotal = 0, eligibleSub = 0, eligibleUnits = 0;

    lines.forEach(function (l) {
      var unit = parseFloat(l.dataset.unit) || 0;
      var qty = parseInt(l.querySelector("[data-qty]") ? l.querySelector("[data-qty]").textContent : "1", 10);
      var total = unit * qty;
      l.querySelector("[data-lineprice]").textContent = unit ? aed(total) : "Free";
      subtotal += total;
      // §6.1 — halo and gift-with-purchase lines are outside the ladder entirely
      if (l.dataset.halo !== "1" && l.dataset.gift !== "1") {
        eligibleSub += total;
        eligibleUnits += qty;
      }
    });

    var pct = eligibleUnits >= 6 ? 15 : eligibleUnits >= 3 ? 10 : 0;
    var disc = eligibleSub * pct / 100;
    var freeShip = subtotal >= 150;
    var ship = freeShip ? 0 : 12;
    var total = subtotal - disc + ship;

    var q = function (s) { return document.querySelector(s); };
    if (q("[data-subtotal]")) q("[data-subtotal]").textContent = aed(subtotal);
    var row = q("[data-tierrow]");
    if (row) {
      row.style.display = pct ? "" : "none";
      if (pct) {
        q("[data-tierpct]").textContent = pct;
        q("[data-tieramt]").textContent = "− " + aed(disc);
      }
    }
    if (q("[data-delivery]")) {
      q("[data-delivery]").textContent = freeShip ? "Free" : aed(12);
      q("[data-delivery]").style.color = freeShip ? "var(--green)" : "";
    }
    if (q("[data-total]")) q("[data-total]").textContent = aed(total);

    /* §10.6 — UAE VAT at 5%, shown as the component inside a tax-inclusive total */
    var VAT_RATE = 0.05, VAT_ON = true;
    var vat = VAT_ON ? total - (total / (1 + VAT_RATE)) : 0;
    if (q("[data-vat]")) q("[data-vat]").textContent = aed(Math.round(vat * 100) / 100);
    var vrow = q("[data-vatrow]");
    if (vrow) vrow.style.display = VAT_ON ? "" : "none";

    /* progress bars */
    var set = function (bar, lb, pctWidth, text) {
      if (q(bar)) q(bar).style.width = Math.min(100, pctWidth) + "%";
      if (q(lb)) q(lb).textContent = text;
    };
    set("[data-p1]", "[data-p1lb]", subtotal / 150 * 100,
        freeShip ? "Unlocked" : aed(150 - subtotal) + " to go");
    set("[data-p2]", "[data-p2lb]", subtotal / 300 * 100,
        subtotal >= 300 ? "Unlocked" : aed(300 - subtotal) + " to go");
    var nextRung = eligibleUnits >= 6 ? 6 : eligibleUnits >= 3 ? 6 : 3;
    set("[data-p3]", "[data-p3lb]", eligibleUnits / nextRung * 100, eligibleUnits + " of " + nextRung);
    if (q("[data-p3txt]")) {
      q("[data-p3txt]").textContent = eligibleUnits >= 6
        ? "Saving 15% — the top rung"
        : "Add " + (nextRung - eligibleUnits) + " more to save " + (nextRung === 6 ? 15 : 10) + "%";
    }

    /* §10.3 — COD withheld over AED 300 */
    var cod = document.querySelector("[data-pay] .off");
    var note = q("[data-codnote]");
    var over = subtotal > 300;
    if (cod) cod.classList.toggle("off", over);
    if (note) note.style.display = over ? "" : "none";
  }
  recalc();

  /* ---------- language toggle: direction is the thing worth seeing ---------- */
  var AR = {
    "Oud Oils": "زيوت العود", "Reserve": "المجموعة الخاصة", "Bakhoor": "بخور",
    "EDP Sprays": "عطور", "Gift Sets": "أطقم الهدايا", "Discovery": "الاكتشاف",
    "Shop by Occasion": "تسوق حسب المناسبة", "Corporate Gifting": "هدايا الشركات",
    "Account": "الحساب", "Wishlist": "المفضلة", "Bag": "الحقيبة",
    "Track order": "تتبع الطلب", "Home": "الرئيسية", "Shop": "المتجر", "Gifts": "الهدايا",
    "All categories": "كل الفئات", "Checkout": "إتمام الشراء", "Add to bag": "أضف إلى الحقيبة",
    "Shop ouds": "تسوق العود", "Build a gift box": "جهّز علبة هدية",
    "Shop by category": "تسوق حسب الفئة", "Shop by scent family": "تسوق حسب العائلة العطرية",
    "Free UAE delivery over AED 150": "توصيل مجاني داخل الإمارات فوق 150 درهم",
    "Cash on delivery": "الدفع عند الاستلام", "Your bag": "حقيبتك", "Total": "الإجمالي",
    "Subtotal": "المجموع الفرعي", "Delivery": "التوصيل", "Free": "مجاني",
    "Continue shopping": "متابعة التسوق", "Summary": "الملخص", "Filters": "عوامل التصفية",
    "Clear all": "مسح الكل", "Gift sets": "أطقم الهدايا", "Oud oils": "زيوت العود"
  };
  var arOn = false;
  function toggleLang(e) {
    e.preventDefault();
    arOn = !arOn;
    var html = document.documentElement;
    html.setAttribute("dir", arOn ? "rtl" : "ltr");
    html.setAttribute("lang", arOn ? "ar" : "en");
    document.body.classList.toggle("ar", arOn);
    document.querySelectorAll("a,span,b,p,h1,h2,h3,h4,h5,button,i,div,label").forEach(function (el) {
      var kids = el.childNodes;
      for (var i = 0; i < kids.length; i++) {
        var n = kids[i];
        if (n.nodeType !== 3) continue;
        var t = n.nodeValue.trim();
        if (!t) continue;
        if (arOn) {
          if (AR[t]) { n.dataset = null; n.__en = t; n.nodeValue = n.nodeValue.replace(t, AR[t]); }
        } else if (n.__en) {
          n.nodeValue = n.nodeValue.replace(AR[n.__en], n.__en);
        }
      }
    });
    document.querySelectorAll("[data-langtoggle]").forEach(function (a) {
      a.textContent = arOn ? "English" : "العربية";
    });
  }
  document.querySelectorAll("[data-langtoggle]").forEach(function (a) {
    a.addEventListener("click", toggleLang);
  });
})();

/* ---------- catalogue comes from assets/catalogue.js, generated by build.py ---------- */
(function () {
  "use strict";
  var CAT = window.BGS_CATALOGUE || {};
  var qs = new URLSearchParams(location.search);
  var T = function (s, v) { var e = document.querySelector(s); if (e) e.textContent = v; };

  /* --- PDP renders whichever product the card named --- */
  var key = qs.get("p");
  if (key && document.querySelector(".pdp")) {
    var pr = CAT[key];
    if (pr) {
      document.title = pr.name + ": " + pr.meta + " | BGS Corner";
      T(".buy h1", pr.name);
      var crumb = document.querySelector("section .eyebrow");
      if (crumb) crumb.textContent = "Home / " + pr.crumb + " / " + pr.name;

      /* the four-line story */
      var d = document.querySelector(".buy p");
      if (d) {
        if (pr.story && pr.story.length) {
          d.className = "story";
          d.innerHTML = pr.story.map(function (l) { return "<span>" + l + "</span>"; }).join("");
        } else {
          d.hidden = true;
        }
      }

      document.querySelectorAll(".buy span").forEach(function (el) {
        if (el.classList.contains("amt")) el.textContent = "AED " + pr.price;
        if (/VAT included/.test(el.textContent)) {
          el.textContent = pr.meta.split("\u00b7").slice(1).join("\u00b7").trim() + " \u00b7 VAT included";
        }
      });
      document.querySelectorAll(".buy .btn.solid").forEach(function (b) {
        b.textContent = "Add to bag: AED " + pr.price;
      });

      /* the sticky bar carries the same product, not the page default */
      var sbn = document.querySelector("[data-sbname]");
      var sbm = document.querySelector("[data-sbmeta]");
      if (sbn) sbn.textContent = pr.name;
      if (sbm) {
        sbm.textContent =
          "AED " + pr.price + " \u00b7 " +
          pr.meta.split("\u00b7").slice(1).join("\u00b7").trim();
      }

      var sizeWrap = document.querySelector(".buy .sizes");
      if (sizeWrap) {
        if (pr.sizes) {
          var psel = pr.sizes.findIndex(function (x) { return x.replace(/&middot;/g, "\u00b7").trim().endsWith("AED " + pr.price); });
          if (psel < 0) psel = 0;
          sizeWrap.innerHTML = pr.sizes.map(function (x, i) {
            return '<button type="button"' + (i === psel ? ' class="on"' : '') +
                   ' data-size="' + x + '">' + x + "</button>";
          }).join("");
        } else {
          var sb = sizeWrap.closest(".sizeblock");
          if (sb) sb.hidden = true;
        }
      }

      /* The gallery is built from the image list, not from a fixed four slots.
         The markup ships four placeholders; a product with one photograph was
         showing that photograph plus three empty boxes and a counter reading
         "3/1". Slides, thumbnails and the counter all follow the real count,
         and with a single image the thumbs, arrows and counter are hidden
         because there is nothing to move between. */
      var imgs = pr.images || [];
      var main = document.querySelector(".galmain");
      var thumbs = document.querySelector(".galthumbs");
      if (main && imgs.length) {
        var esc = function (t) { return String(t).replace(/"/g, "&quot;"); };
        var nav = main.querySelectorAll(".galnav, .galcount");
        main.querySelectorAll("[data-gs]").forEach(function (n) { n.remove(); });
        imgs.forEach(function (src, i) {
          var d = document.createElement("div");
          d.className = "galslide" + (i === 0 ? " on" : "");
          d.setAttribute("data-gs", i);
          d.innerHTML = '<img src="assets/img/' + src + '" alt="' + esc(pr.name) +
            '" loading="' + (i ? "lazy" : "eager") + '" decoding="async">';
          main.insertBefore(d, nav[0] || null);
        });
        if (thumbs) {
          thumbs.innerHTML = imgs.map(function (src, i) {
            return '<button type="button" class="galthumb' + (i === 0 ? " on" : "") +
              '" data-gt="' + i + '" aria-label="Image ' + (i + 1) + '">' +
              '<img src="assets/img/' + src.replace(".jpg", "-card.jpg") +
              '" alt="" loading="lazy" decoding="async"></button>';
          }).join("");
          thumbs.style.gridTemplateColumns = "repeat(" + Math.min(imgs.length, 6) + ",1fr)";
          thumbs.hidden = imgs.length < 2;
        }
        var single = imgs.length < 2;
        main.querySelectorAll(".galnav").forEach(function (b2) { b2.hidden = single; });
        var gc = main.querySelector(".galcount");
        if (gc) {
          gc.hidden = single;
          gc.innerHTML = '<b data-gnum>1</b>/' + imgs.length;
        }
      }

      /* availability + batch rows */
      var rows = document.querySelectorAll(".buy .kv div");
      rows.forEach(function (r) {
        var k = r.firstElementChild ? r.firstElementChild.textContent : "";
        var v = r.lastElementChild;
        if (/Availability/.test(k)) {
          if (typeof pr.stock === "number") {
            v.innerHTML = pr.stock <= 5
              ? '<b style="color:var(--red)">Only ' + pr.stock + " left</b>"
              : '<span style="color:var(--green);font-weight:600">In stock</span>';
          }
        }
        if (/Batch number/.test(k) && pr.sku) { r.firstElementChild.textContent = "Barcode"; v.textContent = pr.sku; }
      });

      /* scent pyramid: fill the three note slots, or show the note line */
      if (pr.top || pr.heart || pr.base) {
        [["top", pr.top], ["heart", pr.heart], ["base", pr.base]].forEach(function (t) {
          var el = document.querySelector('[data-note="' + t[0] + '"]');
          if (el) el.textContent = t[1] || "\u2014";
        });
      } else {
        var grid = document.querySelector('[data-panel="pyramid"] .grid');
        if (grid) grid.hidden = true;
        var pn = document.querySelector("[data-pyrnote]");
        if (pn) pn.hidden = false;
      }
      /* declared ingredients go inside the Ingredients tab */
      if (pr.ing) {
        var ing = document.querySelector("[data-ingpanel]");
        if (ing) ing.innerHTML = '<span class="eyebrow">Declared ingredients</span>' +
          '<p style="margin:8px 0 0">' + pr.ing + "</p>";
      }
    }
  }

  /* --- collection reflects the family or category it was opened with --- */
  var fam = qs.get("family"), cat = qs.get("cat");
  if ((fam || cat) && document.querySelector(".plp")) {
    var label = (fam || cat).replace(/-/g, " ").replace(/\band\b/, "&")
                .replace(/\b\w/g, function (c) { return c.toUpperCase(); });
    var h = document.querySelector("section .sec-h h2");
    if (h) h.textContent = label;
    var cr = document.querySelector("section .eyebrow");
    if (cr) cr.textContent = "Home / " + (fam ? "Scent families" : "Categories") + " / " + label;
    var pills = document.querySelector(".pills");
    if (pills) pills.innerHTML = '<span class="pill on">' + label + " ×</span>" + pills.innerHTML;
    document.querySelectorAll(".fbox label").forEach(function (l) {
      if (l.textContent.trim().toLowerCase().indexOf(label.toLowerCase()) === 0) {
        var cb = l.querySelector("input"); if (cb) cb.checked = true;
      }
    });
    document.title = label + " | BGS Corner";
  }
})();


/* ---------- mobile filter drawer + sticky buy bar ---------- */
(function () {
  "use strict";
  var open = function (v) { document.body.classList.toggle("filters-open", v); };
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-openfilters]")) { e.preventDefault(); open(true); }
    else if (e.target.closest("[data-closefilters]")) { e.preventDefault(); open(false); }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") open(false);
  });
  /* applied-count badge tracks the facets */
  var count = function () {
    var n = document.querySelectorAll(".fbox input:checked").length;
    document.querySelectorAll(".fcount").forEach(function (b) {
      b.textContent = n; b.style.display = n ? "" : "none";
    });
  };
  document.addEventListener("change", function (e) {
    if (e.target.closest(".fbox")) count();
  });
  count();
  if (document.querySelector(".stickybuy")) document.body.classList.add("has-sticky");
})();


/* sticky buy bar: always available on mobile — the one control that must never
   require scrolling to find */
(function () {
  "use strict";
  if (document.querySelector(".stickybuy")) document.body.classList.add("has-sticky");
})();


/* ---------- hero carousel ---------- */
(function () {
  "use strict";
  var root = document.querySelector("[data-carousel]");
  if (!root) return;
  var slides = root.querySelectorAll("[data-slide]");
  var dots = root.querySelectorAll("[data-dot]");
  var no = root.querySelector("[data-slideno]");
  var i = 0, timer;

  function show(n) {
    i = (n + slides.length) % slides.length;
    slides.forEach(function (s, k) { s.classList.toggle("on", k === i); });
    dots.forEach(function (d, k) { d.classList.toggle("on", k === i); });
    if (no) no.textContent = i + 1;
  }
  function go(step) { show(i + step); rest(); }
  function rest() {
    clearInterval(timer);
    timer = setInterval(function () { show(i + 1); }, 7000);
  }

  root.querySelector("[data-prev]").addEventListener("click", function (e) { e.preventDefault(); go(-1); });
  root.querySelector("[data-next]").addEventListener("click", function (e) { e.preventDefault(); go(1); });
  dots.forEach(function (d) {
    d.addEventListener("click", function () { show(+d.dataset.dot); rest(); });
  });

  /* swipe, since most of this traffic is a thumb */
  var x0 = null;
  root.addEventListener("touchstart", function (e) { x0 = e.touches[0].clientX; }, { passive: true });
  root.addEventListener("touchend", function (e) {
    if (x0 === null) return;
    var dx = e.changedTouches[0].clientX - x0;
    if (Math.abs(dx) > 45) go(dx < 0 ? 1 : -1);
    x0 = null;
  }, { passive: true });

  root.addEventListener("mouseenter", function () { clearInterval(timer); });
  root.addEventListener("mouseleave", rest);
  show(0); rest();
})();


/* ---------- scent quiz (brief §8.3) ----------
   Answers map to the §4 taxonomy, then score against the nine real aroma
   profiles in BGS_Perfume_Ingredients.xlsx. Those profiles are estimated by
   the sheet's own author from declared allergens, not official pyramids. */
(function () {
  "use strict";
  var root = document.querySelector("[data-quiz]");
  if (!root) return;

  var PROFILES = [
    { name: "Be Mine", code: "6297000197739", aud: "Her",
      notes: "Citrus, rose, jasmine-like white floral, soft sweet/tonka",
      f: ["citrus","rose","floral","sweet"] },
    { name: null, code: "6297000197777", aud: "Her",
      notes: "Rose and jasmine-like florals, lemon/citrus, clove spice, soft sweet/tonka",
      f: ["rose","floral","citrus","spice","sweet"] },
    { name: null, code: "6297000197814", aud: "Her",
      notes: "Powdery violet, green violet-leaf, lily-of-the-valley, rose and citrus",
      f: ["violet","floral","rose","citrus"] },
    { name: null, code: "6297000197784", aud: "Unisex",
      notes: "Cinnamon and clove spice, citrus, rosy floral and sweet tonka-like warmth",
      f: ["spice","citrus","rose","sweet"] },
    { name: null, code: "6297000197807", aud: "Unisex",
      notes: "Rose/floral, lemon-citrus, clove spice and warm balsamic-amber facets",
      f: ["rose","floral","citrus","spice","amber"] },
    { name: null, code: "6297000197760", aud: "Him",
      notes: "Clove-like spice, bright citrus and aromatic floral/lavender facets",
      f: ["spice","citrus","lavender"] },
    { name: null, code: "6297000197753", aud: "Unisex",
      notes: "Lemon-citrus, aromatic floral/lavender and warm clove-like spice",
      f: ["citrus","lavender","spice"] },
    { name: null, code: "6297000197746", aud: "Unisex",
      notes: "Clean, bright lemon-citrus profile", f: ["citrus"] },
    { name: null, code: "6297000197791", aud: "Unisex",
      notes: "Citrus, aromatic floral/lavender, rose and soft sweet tonka-like warmth",
      f: ["citrus","lavender","rose","sweet"] }
  ];

  /* answer -> facets it favours, and the §4 labels to display */
  var MAP = {
    daily:{f:["citrus"],occ:"Daily"}, office:{f:["citrus","violet"],occ:"Office"},
    evening:{f:["amber","spice","sweet"],occ:"Evening"}, majlis:{f:["amber","spice"],occ:"Majlis"},
    bold:{f:["spice","amber"],tone:"Bold"}, soft:{f:["violet","floral"],tone:"Soft"},
    warm:{f:["spice","amber","sweet"],tone:"Warm"}, fresh:{f:["citrus","lavender"],tone:"Fresh"},
    citrus:{f:["citrus","citrus"],fam:"Fresh & Citrus"}, rose:{f:["rose","floral","floral"],fam:"Floral Veil"},
    spice:{f:["spice","spice"],fam:"Amber & Spice"}, sweet:{f:["sweet","sweet"],fam:"Sweet & Gourmand"},
    violet:{f:["violet","violet"],fam:"Musk & Clean"}, wood:{f:["amber","amber"],fam:"Oud & Woods"},
    intimate:{f:["violet"],sil:"Intimate"}, noticeable:{f:[],sil:"Noticeable"},
    room:{f:["spice","amber"],sil:"Room-filling"},
    summer:{f:["citrus","lavender"],sea:"Summer-safe"}, winter:{f:["amber","spice","sweet"],sea:"Winter"},
    both:{f:[],sea:"All year"}
  };

  var answers = [], step = 0;
  var cards = root.querySelectorAll(".qcard");
  var bar = root.querySelector("[data-qbar]"), num = root.querySelector("[data-qnum]");
  var back = root.querySelector("[data-qback]");
  var res = document.querySelector("[data-qresult]");

  function show(n) {
    step = n;
    cards.forEach(function (c, i) { c.hidden = i !== n; });
    bar.style.width = ((n + 1) / cards.length * 100) + "%";
    num.textContent = n + 1;
    back.hidden = n === 0;
  }

  root.addEventListener("click", function (e) {
    var b = e.target.closest("[data-a]");
    if (b) {
      answers[step] = b.dataset.a;
      if (step + 1 < cards.length) show(step + 1); else finish();
      return;
    }
    if (e.target.closest("[data-qback]")) show(Math.max(0, step - 1));
  });

  function finish() {
    var want = [], labels = {};
    answers.forEach(function (a) {
      var m = MAP[a]; if (!m) return;
      want = want.concat(m.f);
      ["occ","tone","fam","sil","sea"].forEach(function (k) { if (m[k]) labels[k] = m[k]; });
    });

    /* `want` carries duplicates on purpose - a facet named twice weighs twice.
       The score shown to a customer counts distinct facets, which is what the
       sentence claims. */
    var uniq = want.filter(function (f, i) { return want.indexOf(f) === i; });
    var best = null;
    PROFILES.forEach(function (pr) {
      var weighted = want.filter(function (f) { return pr.f.indexOf(f) !== -1; }).length;
      var shared = uniq.filter(function (f) { return pr.f.indexOf(f) !== -1; }).length;
      if (!best || weighted > best.weighted) best = { pr: pr, weighted: weighted, shared: shared };
    });
    best.total = uniq.length;

    var q = function (sel) { return res.querySelector(sel); };
    q("[data-rtitle]").textContent = (labels.fam || "Your scent") + " · " + (labels.tone || "");
    q("[data-rpills]").innerHTML = ["fam","tone","occ","sil","sea"]
      .filter(function (k) { return labels[k]; })
      .map(function (k) { return '<span class="pill on">' + labels[k] + "</span>"; }).join("");
    q("[data-rname]").innerHTML = best.pr.name
      ? best.pr.name
      : 'EDP spray <span class="slot">name not on the packaging</span>';
    q("[data-rmeta]").textContent = "EDP spray · 50 ml · " + best.pr.aud;
    q("[data-rnotes]").textContent = best.pr.notes;
    q("[data-rcode]").textContent = best.pr.code;
    q("[data-rscore]").textContent = best.shared + " of " + best.total + " facets shared";
    root.hidden = true; res.hidden = false;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  res.addEventListener("click", function (e) {
    if (e.target.closest("[data-qretake]")) {
      answers = []; res.hidden = true; root.hidden = false; show(0);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  });

  show(0);
})();


/* ---------- PDP gallery: thumbnails select, arrows cycle ---------- */
(function () {
  "use strict";
  var root = document.querySelector("[data-gallery]");
  if (!root) return;
  var slides = root.querySelectorAll("[data-gs]");
  var thumbs = root.querySelectorAll("[data-gt]");
  var num = root.querySelector("[data-gnum]");
  var i = 0;

  function show(n) {
    i = (n + slides.length) % slides.length;
    slides.forEach(function (s, k) { s.classList.toggle("on", k === i); });
    thumbs.forEach(function (t, k) {
      t.classList.toggle("on", k === i);
      t.setAttribute("aria-selected", k === i ? "true" : "false");
    });
    if (num) num.textContent = i + 1;
  }

  /* manual navigation: move, then reset the autoplay countdown so it doesn't
     yank the slide out from under the visitor a moment later */
  function go(n) { show(n); start(); }

  thumbs.forEach(function (t) {
    t.addEventListener("click", function () { go(+t.dataset.gt); });
  });
  root.querySelector("[data-gprev]").addEventListener("click", function () { go(i - 1); });
  root.querySelector("[data-gnext]").addEventListener("click", function () { go(i + 1); });

  /* arrow keys when the gallery has focus, and swipe on touch */
  root.addEventListener("keydown", function (e) {
    if (e.key === "ArrowLeft") { go(i - 1); }
    if (e.key === "ArrowRight") { go(i + 1); }
  });
  var x0 = null;
  root.addEventListener("touchstart", function (e) { x0 = e.touches[0].clientX; }, { passive: true });
  root.addEventListener("touchend", function (e) {
    if (x0 === null) return;
    var dx = e.changedTouches[0].clientX - x0;
    if (Math.abs(dx) > 40) go(i + (dx < 0 ? 1 : -1));
    x0 = null;
  }, { passive: true });

  /* autoplay: advance every AUTO ms. Pauses on hover and while the tab is
     hidden, resets on any manual navigation, and stays off for single-image
     products or visitors who prefer reduced motion. */
  var AUTO = 5000, timer = null;
  var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function stop() { if (timer) { clearInterval(timer); timer = null; } }
  function start() {
    stop();
    if (slides.length < 2 || still) return;
    timer = setInterval(function () { if (!document.hidden) show(i + 1); }, AUTO);
  }
  root.addEventListener("mouseenter", stop);
  root.addEventListener("mouseleave", start);
  document.addEventListener("visibilitychange", function () { if (document.hidden) { stop(); } else { start(); } });

  show(0);
  start();
})();


/* ---------- PDP: keep the buy decision above the fold ----------------------
   The spec table is four rows that are all placeholders on most products, and
   it used to sit between the price and Add to bag. It is below the button now,
   and when nothing in it has a value it collapses to a single honest line
   rather than four rows saying "not set".
--------------------------------------------------------------------------- */
(function () {
  "use strict";
  var specs = document.querySelector("[data-specs]");
  if (!specs) return;
  var rows = [].slice.call(specs.querySelectorAll("div"));
  var withValue = rows.filter(function (r) {
    var v = r.lastElementChild;
    return v && !v.querySelector(".slot") && v.textContent.trim() !== "";
  });
  if (withValue.length === 0) {
    specs.hidden = true;
  } else {
    rows.forEach(function (r) {
      if (withValue.indexOf(r) < 0) r.hidden = true;
    });
  }
})();


/* ---------- size chips pick a variant ---------------------------------------
   The chips carry a price, so choosing one has to move the price and the
   button with it. On a product card the whole tile is a link, so the click has
   to be stopped before it navigates.
--------------------------------------------------------------------------- */
(function () {
  "use strict";
  document.addEventListener("click", function (e) {
    var chip = e.target.closest("[data-size]");
    if (!chip || !chip.parentElement) return;
    e.preventDefault(); e.stopPropagation();

    var row = chip.parentElement;
    row.querySelectorAll("[data-size]").forEach(function (x) { x.classList.remove("on"); });
    chip.classList.add("on");

    var m = chip.textContent.match(/([\d,]+)\s*$/);
    if (!m) return;
    var scope = chip.closest(".buy") || chip.closest(".p");
    if (!scope) return;

    var amt = scope.querySelector(".amt") || scope.querySelector(".pr b");
    if (amt) amt.textContent = "AED " + m[1];

    scope.querySelectorAll(".btn").forEach(function (b) {
      if (/Add to bag: AED/.test(b.textContent)) b.textContent = "Add to bag: AED " + m[1];
    });
    var sbm = document.querySelector("[data-sbmeta]");
    if (sbm && scope.classList.contains("buy")) {
      sbm.textContent = sbm.textContent.replace(/AED [\d,]+/, "AED " + m[1]);
    }
  });
})();


/* ---------- collection: a real filter engine -------------------------------
   The collection page shipped a hardcoded oud-oils grid, so every category
   link relabelled the heading and still showed the same 11 products. This
   filters the real catalogue. Only facets the content layer carries are
   offered: category and price for all products, gender for the sprays. State
   lives in the URL so a filtered view is shareable.
--------------------------------------------------------------------------- */
(function () {
  "use strict";
  var grid = document.querySelector("[data-grid]");
  if (!grid) return;
  var CAT = window.BGS_CATALOGUE || {};

  var CAT_LABEL = { "oud-oils": "Oud oils", "reserve": "Reserve", "bakhoor": "Bakhoor",
                    "edp": "EDP sprays", "gift-sets": "Gift sets" };
  var CAT_INTRO = {
    "oud-oils": "Alcohol-free perfume oil in 3 ml and 6 ml.",
    "reserve":  "The blends that sit outside every discount the shop runs.",
    "bakhoor":  "Bakhoor for the home, in 20 g to 50 g tins.",
    "edp":      "Eau de parfum sprays, 50 ml, with declared note profiles.",
    "gift-sets": "Wrapped sets, built from the house blends." };

  function params() {
    var q = new URLSearchParams(location.search),
        st = { cat: [], price: [], gender: [], ready: false, sort: "featured", q: "" };
    ["cat", "price", "gender"].forEach(function (k) {
      var v = q.get(k); if (v) st[k] = v.split(",").filter(Boolean);
    });
    if (q.get("ready") === "1") st.ready = true;
    if (q.get("sort")) st.sort = q.get("sort");
    if (q.get("q")) st.q = q.get("q");
    return st;
  }
  function write(st) {
    var q = new URLSearchParams();
    ["cat", "price", "gender"].forEach(function (k) { if (st[k].length) q.set(k, st[k].join(",")); });
    if (st.ready) q.set("ready", "1");
    if (st.sort !== "featured") q.set("sort", st.sort);
    if (st.q) q.set("q", st.q);
    history.replaceState(null, "", location.pathname + (q.toString() ? "?" + q : ""));
  }
  function inBand(pn, band) { var p = band.split("-"); return pn >= +p[0] && pn <= +p[1]; }
  function match(pr, st) {
    if (st.cat.length && st.cat.indexOf(pr.cat) < 0) return false;
    if (st.gender.length && (!pr.gender || st.gender.indexOf(pr.gender) < 0)) return false;
    if (st.price.length && !st.price.some(function (b) { return inBand(pr.pn, b); })) return false;
    if (st.ready && !(pr.stock > 0)) return false;
    if (st.q && pr.name.toLowerCase().indexOf(st.q.toLowerCase()) < 0) return false;
    return true;
  }
  function esc(t) {
    return String(t).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }
  var HEART = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M12 20s-7-4.5-7-9a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 4.5-7 9-7 9z"/></svg>';
  function photo(pr) {
    var imgs = pr.images || [];
    if (!imgs.length) return '<span class="none">Product image</span>';
    var c = function (n) { return n.replace(".jpg", "-card.jpg"); };
    var o = '<img class="ph-a" src="assets/img/' + c(imgs[0]) + '" alt="' + esc(pr.name) +
            '" loading="lazy" decoding="async" width="520" height="520">';
    if (imgs.length > 1)
      o += '<img class="ph-b" src="assets/img/' + c(imgs[1]) +
           '" alt="" aria-hidden="true" loading="lazy" decoding="async" width="520" height="520">';
    return o;
  }
  function cardHTML(key, pr) {
    var badge = pr.halo ? '<span class="badge res">Reserve</span>'
              : (pr.stock > 0 && pr.stock <= 5) ? '<span class="badge low">' + pr.stock + ' left</span>' : '';
    var ssel = 0;
    if (pr.sizes && pr.sizes.length) {
      ssel = pr.sizes.findIndex(function (x) { return x.replace(/&middot;/g, "\u00b7").trim().endsWith("AED " + pr.price); });
      if (ssel < 0) ssel = 0;
    }
    var sizes = (pr.sizes && pr.sizes.length)
      ? '<div class="sizes">' + pr.sizes.map(function (sz, i) {
          return '<button type="button"' + (i === ssel ? ' class="on"' : "") + ' data-size="' + esc(sz) + '">' + esc(sz) + "</button>"; }).join("") + '</div>'
      : '';
    var notes = pr.top ? '<span class="notes">' + esc(pr.top) + "</span>" : "";
    return '<a class="p" href="product.html?p=' + key + '">' +
      '<div class="ph">' + photo(pr) + badge +
      '<button type="button" class="heart" data-wish="' + key + '" aria-pressed="false" aria-label="Save ' + esc(pr.name) + ' to wishlist">' + HEART + "</button></div>" +
      '<div class="b"><span class="meta">' + esc(pr.meta) + "</span><span class=\"nm\">" + esc(pr.name) + "</span>" + notes + sizes +
      '<div class="pr"><b>AED ' + esc(pr.price) + "</b></div>" +
      (pr.halo ? '<span class="norm">Never discounted</span>' : "") +
      '<span class="btn sm solid" style="margin-top:4px">Add to bag</span></div></a>';
  }
  function pillsFor(st) {
    var out = [];
    st.cat.forEach(function (c) { out.push(["cat", c, CAT_LABEL[c] || c]); });
    st.gender.forEach(function (g) { out.push(["gender", g, g]); });
    st.price.forEach(function (b) { var p = b.split("-");
      out.push(["price", b, +p[1] > 99998 ? "AED " + p[0] + "+" : "AED " + p[0] + "-" + p[1]]); });
    if (st.q) out.push(["q", st.q, '"' + st.q + '"']);
    return out;
  }
  function render() {
    var st = params();
    var keys = Object.keys(CAT).filter(function (k) { return match(CAT[k], st); });
    if (st.sort === "price-asc")  keys.sort(function (a, b) { return CAT[a].pn - CAT[b].pn; });
    if (st.sort === "price-desc") keys.sort(function (a, b) { return CAT[b].pn - CAT[a].pn; });
    if (st.sort === "name")       keys.sort(function (a, b) { return CAT[a].name.localeCompare(CAT[b].name); });
    grid.innerHTML = keys.map(function (k) { return cardHTML(k, CAT[k]); }).join("");
    var empty = document.querySelector("[data-empty]");
    if (empty) empty.hidden = keys.length > 0;
    grid.hidden = keys.length === 0;
    document.querySelectorAll("[data-count]").forEach(function (n) { n.textContent = keys.length; });

    var one = st.cat.length === 1 ? st.cat[0] : null;
    var title = one ? CAT_LABEL[one] : "All products";
    var t = document.querySelector("[data-title]"), intro = document.querySelector("[data-intro]"),
        cr = document.querySelector("[data-crumb]");
    if (t) t.textContent = title;
    if (intro) intro.textContent = one ? CAT_INTRO[one]
      : "Every blend in the shop: oud oils, Reserve, bakhoor, EDP sprays and gift sets.";
    if (cr) cr.textContent = one ? "Home / Categories / " + title : "Home / All products";
    document.title = title + " | BGS Corner";

    document.querySelectorAll("[data-facet]").forEach(function (cb) {
      cb.checked = st[cb.getAttribute("data-facet")].indexOf(cb.value) > -1; });
    var sortSel = document.querySelector("[data-sort]"); if (sortSel) sortSel.value = st.sort;

    var pills = document.querySelector("[data-pills]"), list = pillsFor(st);
    if (pills) {
      pills.innerHTML = list.map(function (p) {
        return '<button type="button" class="pill on" data-rm="' + p[0] + '" data-val="' + esc(p[1]) +
               '">' + esc(p[2]) + ' <span aria-hidden="true">&times;</span><span class="none-visual"> remove filter</span></button>';
      }).join("") +
      '<button type="button" class="pill' + (st.ready ? " on" : "") + '" data-toggle="ready">Ready today</button>';
    }
    var fc = document.querySelector("[data-fcount]");
    if (fc) { fc.textContent = list.length + (st.ready ? 1 : 0); fc.hidden = (list.length + (st.ready ? 1 : 0)) === 0; }
    if (window.BGSWish) window.BGSWish.sync();
  }

  document.addEventListener("click", function (e) {
    var st = params(), touched = false;
    var rm = e.target.closest("[data-rm]");
    if (rm) {
      var k = rm.getAttribute("data-rm"), v = rm.getAttribute("data-val");
      if (k === "q") st.q = ""; else st[k] = st[k].filter(function (x) { return x !== v; });
      touched = true;
    }
    if (e.target.closest("[data-toggle]")) { st.ready = !st.ready; touched = true; }
    if (e.target.closest("[data-clearall]")) { st = { cat: [], price: [], gender: [], ready: false, sort: st.sort, q: "" }; touched = true; }
    if (touched) { e.preventDefault(); write(st); render(); }
  });
  document.addEventListener("change", function (e) {
    var cb = e.target.closest("[data-facet]");
    if (cb) {
      var st = params(), k = cb.getAttribute("data-facet");
      if (cb.checked) { if (st[k].indexOf(cb.value) < 0) st[k].push(cb.value); }
      else st[k] = st[k].filter(function (x) { return x !== cb.value; });
      write(st); render(); return;
    }
    var sel = e.target.closest("[data-sort]");
    if (sel) { var s2 = params(); s2.sort = sel.value; write(s2); render(); }
  });
  render();
})();


/* ---------- wishlist hearts, on every page ---------------------------------
   The heart sits inside the card's own link, so its handler must stop the
   click reaching the anchor. State is per browser; there is no account yet.
--------------------------------------------------------------------------- */
(function () {
  "use strict";
  function get() { try { return JSON.parse(localStorage.getItem("bgs_wish") || "[]"); } catch (e) { return []; } }
  function set(a) { try { localStorage.setItem("bgs_wish", JSON.stringify(a)); } catch (e) {} }
  function sync() {
    var w = get();
    document.querySelectorAll("[data-wish]").forEach(function (b) {
      var on = w.indexOf(b.getAttribute("data-wish")) > -1;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    document.querySelectorAll("[data-wishcount]").forEach(function (c) { c.textContent = w.length; c.hidden = w.length === 0; });
  }
  window.BGSWish = { get: get, sync: sync };
  document.addEventListener("click", function (e) {
    var wish = e.target.closest("[data-wish]");
    if (!wish) return;
    e.preventDefault(); e.stopPropagation();
    var k = wish.getAttribute("data-wish"), w = get(), i = w.indexOf(k);
    if (i > -1) w.splice(i, 1); else w.push(k);
    set(w); sync();
  });
  sync();
})();


/* ---------- PDP tabs: five spans that could not be switched ---------- */
(function () {
  "use strict";
  var tabs = document.querySelectorAll("[data-tab]");
  if (!tabs.length) return;
  function show(name) {
    tabs.forEach(function (t) {
      var on = t.getAttribute("data-tab") === name;
      t.classList.toggle("on", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll("[data-panel]").forEach(function (pnl) {
      pnl.hidden = pnl.getAttribute("data-panel") !== name;
    });
  }
  var want = new URLSearchParams(location.search).get("tab");
  if (want && document.querySelector('[data-tab="' + want + '"]')) show(want);
  tabs.forEach(function (t) {
    t.addEventListener("click", function () { show(t.getAttribute("data-tab")); });
    t.addEventListener("keydown", function (e) {
      var list = [].slice.call(tabs), i = list.indexOf(t);
      if (e.key === "ArrowRight") { e.preventDefault(); var nx = list[(i + 1) % list.length]; nx.focus(); nx.click(); }
      if (e.key === "ArrowLeft")  { e.preventDefault(); var pv = list[(i - 1 + list.length) % list.length]; pv.focus(); pv.click(); }
    });
  });
})();


/* ---------- checkout: selectable payment method ---------- */
(function () {
  "use strict";
  var pick = document.querySelector("[data-paypick]");
  if (!pick) return;
  pick.addEventListener("click", function (e) {
    var b = e.target.closest("button");
    if (!b) return;
    pick.querySelectorAll("button").forEach(function (x) { x.classList.remove("on"); });
    b.classList.add("on");
  });
})();


/* ---------- SEO: keep faceted collection URLs out of the index -------------
   The filter engine applies ?cat=&price=&gender=… client-side; the brief
   (§14.4) wants those multi-facet combinations noindex,follow with a canonical
   to the clean collection page, to prevent crawl explosion.
--------------------------------------------------------------------------- */
(function () {
  "use strict";
  if (!/collection\.html$/.test(location.pathname)) return;
  if (!location.search) return;
  var m = document.createElement("meta");
  m.name = "robots"; m.content = "noindex,follow";
  document.head.appendChild(m);
})();


/* ---------- track order + corporate enquiry (front-end only) ----------------
   There is no backend, and these say so rather than pretending. Find-my-order
   validates the number and reveals the standard status sequence; the corporate
   form validates an email and acknowledges the enquiry.
--------------------------------------------------------------------------- */
(function () {
  "use strict";
  var find = document.querySelector("[data-findorder]");
  if (find) {
    find.addEventListener("click", function () {
      var num = (document.querySelector("[data-ordernum]") || {}).value || "";
      var phone = (document.querySelector("[data-orderphone]") || {}).value || "";
      var out = document.querySelector("[data-findresult]");
      out.hidden = false;
      if (!num.trim() && !phone.trim()) { out.textContent = "Enter your order number, or the phone you ordered with."; return; }
      out.textContent = "Looking for " + (num.trim() || phone.trim()) + ". Live courier tracking connects with the backend; the stages below are the standard sequence your order moves through.";
    });
  }
  var send = document.querySelector("[data-cqsend]");
  if (send) {
    send.addEventListener("click", function () {
      var g = function (k) { var e = document.querySelector('[data-cq="' + k + '"]'); return e ? e.value.trim() : ""; };
      var out = document.querySelector("[data-cqresult]");
      out.hidden = false;
      var email = g("email");
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { out.textContent = "Enter a valid work email so we can reply."; return; }
      out.textContent = "Thank you" + (g("name") ? ", " + g("name") : "") + ". We will come back with a quote" + (g("units") ? " for " + g("units") + " units" : "") + ". This form is front-end only for now; the enquiry is not yet sent anywhere.";
    });
  }
})();
/* ---------- gift box builder ----------------------------------------------
   Was a static mock: two inert "3 slots / 6 slots" pills, three hardcoded
   slots and a total that never moved. The picker cards below it are ordinary
   product links, so adding has to intercept the click the same way the
   wishlist heart does.
--------------------------------------------------------------------------- */
(function () {
  "use strict";
  var slotsHost = document.querySelector("[data-slots]");
  if (!slotsHost) return;
  var CAT = window.BGS_CATALOGUE || {};
  var BOX_FEE = 25;
  var size = 3, picked = [];

  function priceOf(k) { return (CAT[k] && CAT[k].pn) || 0; }

  function renderSlots() {
    var html = "";
    for (var i = 0; i < size; i++) {
      var k = picked[i];
      if (k) {
        html += '<button type="button" class="p slot-filled" data-unpick="' + i + '">' +
          '<div class="ph"><span class="none">Slot ' + (i + 1) + "</span></div>" +
          '<div class="b"><span class="nm">' + CAT[k].name + "</span>" +
          '<span class="notes">AED ' + CAT[k].price + ' &middot; tap to remove</span></div></button>';
      } else {
        html += '<div class="p" style="border-style:dashed"><div class="ph" style="background:var(--alt)">' +
          '<span class="none">Slot ' + (i + 1) + ' empty</span></div>' +
          '<div class="b"><span class="nm" style="color:var(--faint)">Choose a scent</span>' +
          '<span class="notes">Pick from below</span></div></div>';
      }
    }
    slotsHost.innerHTML = html;
    slotsHost.className = "grid " + (size === 6 ? "g3" : "g3");
  }

  function renderSummary() {
    var n = picked.length;
    var scents = picked.reduce(function (t, k) { return t + priceOf(k); }, 0);
    var disc = n >= 3 ? Math.round(scents * 0.10) : 0;
    var total = scents + BOX_FEE - disc;

    var q = function (s) { return document.querySelector(s); };
    q("[data-boxn]").textContent = n + (n === 1 ? " scent" : " scents");
    q("[data-boxscents]").textContent = "AED " + scents;
    var dr = q("[data-boxdisc]");
    dr.style.color = n >= 3 ? "var(--green)" : "var(--faint)";
    dr.querySelector("span:last-child").innerHTML = n >= 3 ? "&minus;AED " + disc : "&minus;10%";
    q("[data-boxtotal]").textContent = "AED " + total;

    var cta = q("[data-boxcta]"), left = size - n;
    if (left > 0) {
      cta.textContent = "Fill " + left + (left === 1 ? " more slot" : " more slots");
      cta.classList.add("ghost"); cta.classList.remove("solid");
    } else {
      cta.textContent = "Add box to bag: AED " + total;
      cta.classList.add("solid"); cta.classList.remove("ghost");
    }
  }

  function render() { renderSlots(); renderSummary(); }

  document.addEventListener("click", function (e) {
    var sz = e.target.closest("[data-boxsize]");
    if (sz) {
      size = +sz.getAttribute("data-boxsize");
      document.querySelectorAll("[data-boxsize]").forEach(function (b) {
        b.classList.toggle("on", b === sz);
      });
      if (picked.length > size) picked = picked.slice(0, size);
      render(); return;
    }

    var un = e.target.closest("[data-unpick]");
    if (un) {
      e.preventDefault();
      picked.splice(+un.getAttribute("data-unpick"), 1);
      render(); return;
    }

    /* the picker cards are product links; adding must not navigate */
    var card = e.target.closest("[data-slots] ~ * .p, .two .grid.g4 .p");
    if (card && card.getAttribute("href")) {
      var key = new URLSearchParams(card.getAttribute("href").split("?")[1] || "").get("p");
      if (!key || !CAT[key]) return;
      e.preventDefault(); e.stopPropagation();
      if (picked.length >= size) {
        var cta = document.querySelector("[data-boxcta]");
        cta.textContent = "Box is full, remove one first";
        setTimeout(renderSummary, 1800);
        return;
      }
      picked.push(key);
      render();
      return;
    }

    var go = e.target.closest("[data-boxcta]");
    if (go && picked.length === size) location.href = "cart.html";
  });

  render();
})();

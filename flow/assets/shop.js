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
        if (pr.story) {
          d.className = "story";
          d.innerHTML = pr.story.map(function (l) { return "<span>" + l + "</span>"; }).join("");
        } else {
          d.innerHTML = '<span class="slot">product story \u2014 not in the source sheet</span>';
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
          sizeWrap.innerHTML = pr.sizes.map(function (x, i) {
            return '<span' + (i === 1 ? ' class="on"' : '') +
                   ' data-size="' + x + '">' + x + "</span>";
          }).join("");
        } else {
          var sb = sizeWrap.closest(".sizeblock");
          if (sb) sb.hidden = true;
        }
      }

      /* the gallery shows this product's photographs; a slide with no image
         keeps its placeholder rather than repeating one that is not its own */
      var imgs = pr.images || [];
      document.querySelectorAll("[data-gs]").forEach(function (slide, i) {
        if (!imgs[i]) return;
        slide.innerHTML = '<img src="assets/img/' + imgs[i] + '" alt="' +
          String(pr.name).replace(/"/g, "&quot;") + '" loading="' + (i ? "lazy" : "eager") +
          '" decoding="async">';
      });
      document.querySelectorAll("[data-gt]").forEach(function (t, i) {
        if (!imgs[i]) return;
        t.innerHTML = '<img src="assets/img/' + imgs[i].replace(".jpg", "-card.jpg") +
          '" alt="" loading="lazy" decoding="async">';
      });
      var gcount = document.querySelector(".galcount");
      if (gcount && imgs.length) gcount.innerHTML = '<b data-gnum>1</b>/' + imgs.length;

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

      /* pyramid + ingredients below the fold */
      var pyr = document.querySelectorAll("section.alt .grid.g3 > div");
      if (pyr.length === 3 && pr.top) {
        [[0, "Top", pr.top], [1, "Heart", pr.heart], [2, "Base", pr.base]].forEach(function (t) {
          var el = pyr[t[0]].querySelector("p");
          if (!el) return;
          if (t[2]) el.textContent = t[2];
          else el.innerHTML = '<span class="slot">not given for this product</span>';
        });
      }
      if (pr.ing) {
        var host = document.querySelector("section.alt .wrap");
        var box = document.createElement("div");
        box.className = "ingbox";
        box.innerHTML = '<span class="eyebrow">Declared ingredients</span><p>' + pr.ing + "</p>";
        host.appendChild(box);
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

  thumbs.forEach(function (t) {
    t.addEventListener("click", function () { show(+t.dataset.gt); });
  });
  root.querySelector("[data-gprev]").addEventListener("click", function () { show(i - 1); });
  root.querySelector("[data-gnext]").addEventListener("click", function () { show(i + 1); });

  /* arrow keys when the gallery has focus, and swipe on touch */
  root.addEventListener("keydown", function (e) {
    if (e.key === "ArrowLeft") { show(i - 1); }
    if (e.key === "ArrowRight") { show(i + 1); }
  });
  var x0 = null;
  root.addEventListener("touchstart", function (e) { x0 = e.touches[0].clientX; }, { passive: true });
  root.addEventListener("touchend", function (e) {
    if (x0 === null) return;
    var dx = e.changedTouches[0].clientX - x0;
    if (Math.abs(dx) > 40) show(i + (dx < 0 ? 1 : -1));
    x0 = null;
  }, { passive: true });

  show(0);
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
    specs.innerHTML = '<div><span>Longevity, sillage, batch and stock</span>' +
      '<span class="slot">not recorded in the source sheet for this product</span></div>';
  } else {
    rows.forEach(function (r) {
      if (withValue.indexOf(r) < 0) r.hidden = true;
    });
  }

  /* the story slot says the same thing; one placeholder is enough */
  var d = document.querySelector("[data-desc]");
  if (d && d.querySelector(".slot") && !d.textContent.replace(/\[.*?\]/g, "").trim()) {
    d.hidden = true;
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

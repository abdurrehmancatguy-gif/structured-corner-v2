/* BGS Corner - front-end only. No backend, no persistence beyond this tab. */

/* Photo URLs carry the photo's version from catalogue.js (BGS_IMGV), because
   Netlify caches /assets/ for a year: bgsImg("vibe-1.jpg", "-600"). */
function bgsImg(name, suffix) {
  var v = window.BGS_IMGV, h = v && Object.prototype.hasOwnProperty.call(v, name) ? "?v=" + v[name] : "";
  return "assets/img/" + (suffix ? name.replace(/\.jpg$/, suffix + ".jpg") : name) + h;
}
/* catalogue lookup by id, own keys only: "constructor" or "__proto__" in a URL
   or in storage finds nothing, instead of one of Object's built-ins */
function bgsProduct(id) {
  var c = window.BGS_CATALOGUE;
  return c && typeof id === "string" && Object.prototype.hasOwnProperty.call(c, id) ? c[id] : null;
}
/* A store rule from settings.json, which build.py writes into catalogue.js as
   BGS_RULES: bgsRule("gift_with_purchase.threshold", 300). Each fallback is
   the value the shop had before the rules moved into content, so a page with
   an older catalogue.js still prices the bag the way its text says. */
function bgsRule(path, fallback) {
  var v = window.BGS_RULES;
  path.split(".").forEach(function (k) {
    v = v && typeof v === "object" && Object.prototype.hasOwnProperty.call(v, k) ? v[k] : undefined;
  });
  return v !== null && typeof v === typeof fallback && Array.isArray(v) === Array.isArray(fallback) ? v : fallback;
}
/* Page text shop.js writes after load, from pages.json and settings.json,
   which build.py writes into catalogue.js as BGS_COPY:
   bgsCopy("product.share.copied", "Link copied"). Each fallback is the text
   the page had before it moved into content, so a page with an older
   catalogue.js reads as it did. It goes in with textContent, never as markup. */
function bgsCopy(path, fallback) {
  var v = window.BGS_COPY;
  path.split(".").forEach(function (k) {
    v = v && typeof v === "object" && Object.prototype.hasOwnProperty.call(v, k) ? v[k] : undefined;
  });
  return typeof v === "string" && v !== "" ? v : fallback;
}
/* the end of every tab title: " | BGS Corner" */
function bgsTitleSuffix() { return " | " + bgsCopy("title_suffix", "BGS Corner"); }
/* The same text for markup a script builds as a string (the bag lines, the
   gift box slots), escaped so "Wrap & card" reads as typed. */
function bgsCopyHtml(path, fallback) {
  return bgsCopy(path, fallback).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
/* Fills a text's {tokens}: bgsFill("Only {n} left", { n: 3 }). One pass with
   a function, so a visitor's own words (a name, an order number) go in as
   typed and are never read as a token or a replacement pattern. */
function bgsFill(text, vals) {
  return text.replace(/\{([a-z_]+)\}/g, function (m, k) {
    return Object.prototype.hasOwnProperty.call(vals, k) ? String(vals[k]) : m;
  });
}
/* Arabic for text shop.js writes after load. The language toggle swaps what
   is on the page when it is pressed; text written later (a pressed Add, the
   added-to-bag panel) comes through here instead, looked up by its exact
   English in BGS_AR as the toggle looks it up, and stays English without an
   entry. Wrap the literal call, so admin/tests/test_pages.py still sees its
   path: bgsAr(bgsCopy("cart.added.title", "Added to your bag")). A counted
   text is translated as its template, then filled:
   bgsFill(bgsAr(bgsCopy("cart.added.qty", "Qty {n}")), { n: 2 }). */
function bgsAr(en) {
  var d = window.BGS_AR;
  return document.documentElement.lang === "ar" && d && typeof en === "string" &&
    Object.prototype.hasOwnProperty.call(d, en) && typeof d[en] === "string" && d[en] !== "" ? d[en] : en;
}
/* Each feature below runs on its own: an error in one (bad data in storage, a
   missing element) is logged and the rest still work. As one plain script, the
   first throw stopped every feature after it, the bag included. */
function bgsRun(f) { try { f(); } catch (e) { if (window.console) console.error(e); } }
/* Run fn once im has its picture (or has failed, or ms have passed), so a
   carousel that jumps to a slide not yet downloaded fades onto the photo and
   not onto an empty frame. */
function bgsWhenLoaded(im, fn, ms) {
  if (!im || im.complete) { fn(); return; }
  var t, done = function () {
    clearTimeout(t);
    im.removeEventListener("load", done); im.removeEventListener("error", done);
    fn();
  };
  t = setTimeout(done, ms || 2500);
  im.addEventListener("load", done); im.addEventListener("error", done);
}
/* two columns with a 16px wrap and a 13px gap on a phone: 50vw would claim
   187px of a 165px card and send the 520 file where the 360 is enough */
var BGS_CARD_SIZES = "(max-width:560px) calc(50vw - 23px), (max-width:700px) 33vw, (max-width:900px) 25vw, 240px";
bgsRun(function () {
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
  var FREE_AT = bgsRule("free_delivery_over", 150), FEE = bgsRule("delivery_fee", 12);
  var GIFT_AT = bgsRule("gift_with_purchase.threshold", 300);
  var LADDER = bgsRule("volume_ladder", [{ units: 3, percent: 10 }, { units: 6, percent: 15 }]);
  /* the bag's words, from pages.json (BGS_COPY.cart); the sums are the engine's */
  var FREE = bgsCopy("cart.summary.free", "Free"), UNLOCKED = bgsCopy("cart.progress.unlocked", "Unlocked");
  function recalc() {
    var lines = document.querySelectorAll("[data-line]");
    if (!lines.length) return;
    var subtotal = 0, eligibleSub = 0, eligibleUnits = 0;

    lines.forEach(function (l) {
      var unit = parseFloat(l.dataset.unit) || 0;
      var qty = parseInt(l.querySelector("[data-qty]") ? l.querySelector("[data-qty]").textContent : "1", 10);
      var total = unit * qty;
      l.querySelector("[data-lineprice]").textContent = unit ? aed(total) : FREE;
      subtotal += total;
      // §6.1 - halo and gift-with-purchase lines are outside the ladder entirely
      if (l.dataset.halo !== "1" && l.dataset.gift !== "1") {
        eligibleSub += total;
        eligibleUnits += qty;
      }
    });

    /* the ladder's rungs rise in units: the bag earns the last one it reaches */
    var pct = 0, next = null;
    LADDER.forEach(function (r) { if (eligibleUnits >= r.units) pct = r.percent; else if (!next) next = r; });
    var disc = eligibleSub * pct / 100;
    var freeShip = subtotal >= FREE_AT;
    var ship = freeShip ? 0 : FEE;
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
      q("[data-delivery]").textContent = freeShip ? FREE : aed(FEE);
      q("[data-delivery]").style.color = freeShip ? "var(--green)" : "";
    }
    if (q("[data-total]")) q("[data-total]").textContent = aed(total);

    /* §10.6 - UAE VAT at 5%, shown as the component inside a tax-inclusive total */
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
    var toGo = function (amount) {
      return bgsFill(bgsCopy("cart.progress.to_go", "{amount} to go"), { amount: aed(amount) });
    };
    set("[data-p1]", "[data-p1lb]", subtotal / FREE_AT * 100,
        freeShip ? UNLOCKED : toGo(FREE_AT - subtotal));
    set("[data-p2]", "[data-p2lb]", subtotal / GIFT_AT * 100,
        subtotal >= GIFT_AT ? UNLOCKED : toGo(GIFT_AT - subtotal));
    var top = LADDER[LADDER.length - 1], nextRung = next ? next.units : top.units;
    set("[data-p3]", "[data-p3lb]", eligibleUnits / nextRung * 100,
        bgsFill(bgsCopy("cart.progress.ladder_count", "{n} of {goal}"), { n: eligibleUnits, goal: nextRung }));
    if (q("[data-p3txt]")) {
      q("[data-p3txt]").textContent = next
        ? bgsFill(bgsCopy("cart.progress.ladder_next", "Add {n} more to save {pct}%"),
                  { n: nextRung - eligibleUnits, pct: next.percent })
        : bgsFill(bgsCopy("cart.progress.ladder_top", "Saving {pct}%, the top rung"), { pct: top.percent });
    }

    /* §10.3 - COD withheld over AED 300 */
    var cod = document.querySelector("[data-pay] .off");
    var note = q("[data-codnote]");
    var over = subtotal > 300;
    if (cod) cod.classList.toggle("off", over);
    if (note) note.style.display = over ? "" : "none";
  }
  window.BGS_RECALC = recalc;
  recalc();

  /* ---------- language toggle: direction is the thing worth seeing ---------- */
  /* The dictionary is content (content/translations.json), written into
     catalogue.js by build.py: English label text to its Arabic. */
  var AR = window.BGS_AR || {};
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
        /* the "more" arrows point the way the page reads: left in Arabic.
           Put back before the English, which is looked up as it was. */
        if (arOn) {
          if (AR[t]) { n.dataset = null; n.__en = t; n.nodeValue = n.nodeValue.replace(t, AR[t]); }
          if (n.nodeValue.indexOf("→") >= 0) { n.__arw = true; n.nodeValue = n.nodeValue.replace(/→/g, "←"); }
        } else {
          if (n.__arw) { n.__arw = false; n.nodeValue = n.nodeValue.replace(/←/g, "→"); }
          if (n.__en) n.nodeValue = n.nodeValue.replace(AR[n.__en], n.__en);
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
});

/* ---------- catalogue comes from assets/catalogue.js, generated by build.py ---------- */
bgsRun(function () {
  "use strict";
  var CAT = window.BGS_CATALOGUE || {};
  var qs = new URLSearchParams(location.search);
  var T = function (s, v) { var e = document.querySelector(s); if (e) e.textContent = v; };

  /* --- PDP renders whichever product the card named --- */
  var key = qs.get("p");
  if (document.querySelector(".pdp")) {
    var pr = key ? bgsProduct(key) : null;
    if (pr) {
      /* one template serves every product, so its canonical names the bare
         page; point it at this product's own address */
      var canon = document.querySelector('link[rel="canonical"]');
      if (canon) canon.href = new URL("product.html?p=" + encodeURIComponent(key), canon.href).href;
      document.title = pr.name + ": " + pr.meta + bgsTitleSuffix();
      T(".buy h1", pr.name);
      var crumb = document.querySelector("section .eyebrow");
      if (crumb) crumb.textContent = bgsCopy("crumb_home", "Home") + " / " + pr.crumb + " / " + pr.name;

      /* the four-line story, each line put in as text: it is content, never markup */
      var d = document.querySelector("[data-desc]");
      if (d) {
        if (pr.story && pr.story.length) {
          d.className = "story";
          d.textContent = "";
          pr.story.forEach(function (l) {
            var line = document.createElement("span");
            line.textContent = l;
            d.appendChild(line);
          });
        } else {
          d.hidden = true;
        }
      }

      document.querySelectorAll(".buy span").forEach(function (el) {
        if (el.classList.contains("amt")) el.textContent = "AED " + pr.price;
        if (el.classList.contains("permeta")) {
          el.textContent = pr.meta.split("\u00b7").slice(1).join("\u00b7").trim();
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
          /* a size label is content: escaped, so a quote in it cannot end the attribute */
          var sz = function (t) { return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"); };
          sizeWrap.innerHTML = pr.sizes.map(function (x, i) {
            return '<button type="button"' + (i === psel ? ' class="on"' : '') +
                   ' data-size="' + sz(x) + '">' + sz(x) + "</button>";
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
          /* only the first slide loads now: the others are stacked at opacity
             0 and would all download with it, so they wait in data-src until
             the gallery shows them or their neighbour */
          var set = bgsImg(src, "-600") + " 600w, " + bgsImg(src) + " 1000w";
          d.innerHTML = '<img ' + (i ? 'data-src="' + bgsImg(src) + '" data-srcset="' + set + '"'
                                     : 'src="' + bgsImg(src) + '" srcset="' + set + '" fetchpriority="high"') +
            ' sizes="(max-width:700px) 245px, (max-width:900px) 330px, 470px" alt="' + esc(pr.name) +
            '" width="1000" height="1000" decoding="async">';
          main.insertBefore(d, nav[0] || null);
        });
        if (thumbs) {
          thumbs.innerHTML = imgs.map(function (src, i) {
            return '<button type="button" class="galthumb' + (i === 0 ? " on" : "") +
              '" data-gt="' + i + '" aria-label="Image ' + (i + 1) + '">' +
              '<img src="' + bgsImg(src, "-thumb") +
              '" alt="" width="160" height="160" loading="lazy" decoding="async"></button>';
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

      /* availability + batch rows, found by the labels build.py printed from
         the same content, trimmed on both sides as the printed label is */
      var AVAIL = bgsCopy("product.specs.availability", "Availability").trim(),
          BATCH = bgsCopy("product.specs.batch", "Batch number").trim();
      var rows = document.querySelectorAll(".buy .kv div");
      rows.forEach(function (r) {
        var k = r.firstElementChild ? r.firstElementChild.textContent.trim() : "";
        var v = r.lastElementChild;
        if (k === AVAIL) {
          if (typeof pr.stock === "number") {
            var low = pr.stock <= bgsRule("low_stock_at", 5), st = document.createElement(low ? "b" : "span");
            st.setAttribute("style", low ? "color:var(--red)" : "color:var(--green);font-weight:600");
            st.textContent = low ? bgsCopy("product.specs.only_left", "Only {n} left").replace("{n}", pr.stock)
                                 : bgsCopy("product.specs.in_stock", "In stock");
            v.textContent = "";
            v.appendChild(st);
          }
        }
        if (k === BATCH && pr.sku) {
          r.firstElementChild.textContent = bgsCopy("product.specs.barcode", "Barcode");
          v.textContent = pr.sku;
        }
      });

      /* blocks for other kinds of product (data-cats), and the 3 ml
         credit-back note where there is no 3 ml (data-with-size), come out
         rather than hide, so the tabs further down count only what is left */
      document.querySelectorAll("[data-cats]").forEach(function (el) {
        if (el.getAttribute("data-cats").split(" ").indexOf(pr.cat) < 0) el.remove();
      });
      var sizeNames = (pr.sizes || []).map(function (x) {
        return x.replace(/&middot;/g, "\u00b7").split("\u00b7")[0].trim();
      });
      document.querySelectorAll("[data-with-size]").forEach(function (el) {
        if (sizeNames.indexOf(el.getAttribute("data-with-size")) < 0) el.remove();
      });

      /* scent pyramid: fill the three note slots, or show the note line. The
         strip under the buttons ships hidden, having no notes of its own. */
      var topstrip = document.querySelector("[data-notestop]");
      if (topstrip) topstrip.hidden = !(pr.top || pr.heart || pr.base);
      if (pr.top || pr.heart || pr.base) {
        [["top", pr.top], ["heart", pr.heart], ["base", pr.base]].forEach(function (t) {
          document.querySelectorAll('[data-note="' + t[0] + '"]').forEach(function (el) {
            el.textContent = t[1] || "";
            var col = el.closest("[data-notestop] > div");
            if (col) col.hidden = !t[1];
          });
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
        if (ing) {
          var ih = document.createElement("span"), ip = document.createElement("p");
          ih.className = "eyebrow";
          ih.textContent = bgsCopy("product.ingredients.heading", "Declared ingredients");
          ip.setAttribute("style", "margin:8px 0 0");
          ip.textContent = pr.ing;
          ing.textContent = "";
          ing.appendChild(ih);
          ing.appendChild(ip);
        }
      }
    } else {
      /* no id, or one the catalogue does not have (retired, mistyped, or an
         Object built-in): say so, instead of showing the template's
         placeholder product with a button that cannot add it. Everything
         after the product section (the sticky bar, the tabs, the related
         row) describes that placeholder too, so it goes with it. */
      var pdp = document.querySelector(".pdp");
      var nf = document.createElement("div"), nh = document.createElement("h1"),
          np = document.createElement("p"), na = document.createElement("a");
      nf.className = "notfound";
      nh.textContent = bgsCopy("product.not_found.title", "We couldn’t find that product");
      na.className = "btn solid";
      na.setAttribute("href", "collection.html");
      na.textContent = bgsCopy("product.not_found.cta", "See all products");
      np.appendChild(na);
      nf.appendChild(nh);
      nf.appendChild(np);
      pdp.textContent = "";
      pdp.appendChild(nf);
      var sec = pdp.closest("section"), next = sec && sec.nextElementSibling;
      while (next) {
        var gone = next;
        next = next.nextElementSibling;
        if (gone.tagName === "SECTION" || gone.classList.contains("stickybuy")) gone.remove();
      }
      document.body.classList.remove("has-sticky");
      var nfc = document.querySelector("section .eyebrow");
      if (nfc) nfc.textContent = bgsCopy("crumb_home", "Home") + " / " + bgsCopy("product.not_found.crumb", "Products");
      document.title = bgsCopy("product.not_found.page_title", "Product not found") + bgsTitleSuffix();
      var nr = document.createElement("meta"); nr.name = "robots"; nr.content = "noindex";
      document.head.appendChild(nr);
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
});


/* ---------- phone masthead: the search button opens the search row ----------
   On phones the search box sits in a row under the masthead that stays shut
   (flow.css hides it once the "js" class is on the page) until the search
   button in the top right corner opens it. A page showing search results
   keeps it open, so the words searched for stay in view. */
bgsRun(function () {
  var btn = document.querySelector("[data-searchtoggle]");
  var row = document.getElementById("msearch");
  if (!btn || !row) return;
  var input = row.querySelector('input[name="q"]');
  function set(open) {
    row.classList.toggle("open", open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  }
  set(!!new URLSearchParams(location.search).get("q"));
  btn.addEventListener("click", function () {
    var open = !row.classList.contains("open");
    set(open);
    if (open && input) input.focus();
  });
  row.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && row.classList.contains("open")) { set(false); btn.focus(); }
  });
});

/* ---------- mobile filter drawer + sticky buy bar ---------- */
bgsRun(function () {
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
});


/* sticky buy bar: always available on mobile - the one control that must never
   require scrolling to find */
bgsRun(function () {
  "use strict";
  if (document.querySelector(".stickybuy")) document.body.classList.add("has-sticky");
});


/* ---------- hero carousel ---------- */
bgsRun(function () {
  "use strict";
  var root = document.querySelector("[data-carousel]");
  if (!root) return;
  var slides = root.querySelectorAll("[data-slide]");
  var dots = root.querySelectorAll("[data-dot]");
  var no = root.querySelector("[data-slideno]");
  var i = 0, want = 0, timer;

  /* the photographs, one per slide, cross-fading with the copy */
  var shots = root.querySelectorAll(".heroimg .hs");

  function show(n) {
    var t = i = want = (n + slides.length) % slides.length;
    dots.forEach(function (d, k) { d.classList.toggle("on", k === t); });
    if (no) no.textContent = t + 1;
    var c = shots.length, near = document.readyState === "complete";
    shots.forEach(function (im, k) {
      /* hidden slides are display:none until "seen" (flow.css), so they do not
         download with the first; the one showing, and once the page has
         loaded its neighbours, are let in so the fade lands on a decoded
         picture */
      var next = near && (k === (t + 1) % c || k === (t - 1 + c) % c);
      if (k === t || next) im.classList.add("seen");
      if (next) im.loading = "eager";
    });
    /* a dot can jump to a slide nobody has fetched: the copy and the photo
       change together once it is in, unless a later click has moved on */
    bgsWhenLoaded(shots[t], function () {
      if (want !== t) return;
      slides.forEach(function (s, k) { s.classList.toggle("on", k === t); });
      shots.forEach(function (im, k) { im.classList.toggle("on", k === t); });
    });
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
  addEventListener("load", function () {
    var n = shots.length;
    if (n > 1) { shots[1].classList.add("seen"); shots[n - 1].classList.add("seen"); }
  });
});


/* ---------- scent quiz (brief §8.3) ----------
   Answers map to the §4 taxonomy, then score against the nine real aroma
   profiles in BGS_Perfume_Ingredients.xlsx. Those profiles are estimated by
   the sheet's own author from declared allergens, not official pyramids. */
bgsRun(function () {
  "use strict";
  var root = document.querySelector("[data-quiz]");
  var QUIZ = window.BGS_QUIZ;
  if (!root || !QUIZ) return;

  /* The questions, what each answer looks for and the profiles are content
     (content/quiz.json). build.py prints the questions and passes the rest
     here as window.BGS_QUIZ: MAP is answer key -> the facets it favours and
     the label it shows, which the result files under the kind of question it
     answers (family, tone, occasion, sillage, season). A profile names its
     product, whose name, price, meta line and barcode come from the catalogue. */
  var PROFILES = QUIZ.profiles || [];
  var MAP = QUIZ.answers || {};
  var KINDS = QUIZ.kinds || [];
  var R = QUIZ.result || {};
  var CAT = window.BGS_CATALOGUE || {};

  var answers = [], step = 0;
  var cards = root.querySelectorAll(".qcard");
  var bar = root.querySelector("[data-qbar]"), num = root.querySelector("[data-qnum]");
  var back = root.querySelector("[data-qback]");
  var res = document.querySelector("[data-qresult]");
  /* "See it" opens the matched product; the page's own link is kept for
     a match the shop does not sell */
  var see = res.querySelector("[data-rsee]");
  var seeAll = see ? see.getAttribute("href") : "";

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
    answers.forEach(function (a, i) {
      var m = MAP[a]; if (!m) return;
      want = want.concat(m.facets || []);
      if (m.label && KINDS[i]) labels[KINDS[i]] = m.label;
    });

    /* `want` carries duplicates on purpose - a facet named twice weighs twice.
       The score shown to a customer counts distinct facets, which is what the
       sentence claims. */
    var uniq = want.filter(function (f, i) { return want.indexOf(f) === i; });
    /* the match is a product the shop sells (published); if none of the
       profiles' products is, the closest profile still answers, unnamed */
    var onSale = PROFILES.filter(function (pr) { return CAT[pr.product]; });
    var best = null;
    (onSale.length ? onSale : PROFILES).forEach(function (pr) {
      var has = pr.facets || [];
      var weighted = want.filter(function (f) { return has.indexOf(f) !== -1; }).length;
      var shared = uniq.filter(function (f) { return has.indexOf(f) !== -1; }).length;
      if (!best || weighted > best.weighted) best = { pr: pr, weighted: weighted, shared: shared };
    });
    if (!best) return;
    best.total = uniq.length;
    var item = CAT[best.pr.product];

    /* content goes into the result as text, never parsed as markup */
    var q = function (sel) { return res.querySelector(sel); };
    var span = function (cls, text) {
      var s = document.createElement("span"); s.className = cls; s.textContent = text; return s;
    };
    q("[data-rtitle]").textContent = (labels.family || R.title_fallback || "") + " · " + (labels.tone || "");
    var pills = q("[data-rpills]");
    pills.textContent = "";
    ["family","tone","occasion","sillage","season"].forEach(function (k) {
      if (labels[k]) pills.appendChild(span("pill on", labels[k]));
    });
    var name = q("[data-rname]");
    name.textContent = item ? item.name : (R.unnamed || "") + " ";
    if (!item) name.appendChild(span("slot", R.unnamed_slot || ""));
    q("[data-rprice]").textContent = item ? "AED " + item.price : "";
    q("[data-rmeta]").textContent = item ? item.meta : "";
    q("[data-rnotes]").textContent = best.pr.notes;
    q("[data-rcode]").textContent = (item && item.sku) || "";
    if (see) see.setAttribute("href", item ? "product.html?p=" + encodeURIComponent(best.pr.product) : seeAll);
    q("[data-rscore]").textContent = (R.score || "")
      .split("{shared}").join(best.shared).split("{total}").join(best.total);
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
});


/* ---------- PDP gallery: thumbnails select, arrows cycle ---------- */
bgsRun(function () {
  "use strict";
  var root = document.querySelector("[data-gallery]");
  if (!root) return;
  var slides = root.querySelectorAll("[data-gs]");
  var thumbs = root.querySelectorAll("[data-gt]");
  var num = root.querySelector("[data-gnum]");
  var i = 0, want = 0;

  /* slides after the first wait in data-src (see the PDP render above) */
  function arm(k) {
    var s = slides[(k + slides.length) % slides.length];
    var im = s && s.querySelector("img[data-src]");
    if (!im) return;
    im.srcset = im.getAttribute("data-srcset"); im.src = im.getAttribute("data-src");
    im.removeAttribute("data-src"); im.removeAttribute("data-srcset");
  }
  /* the neighbours both ways, since the prev arrow from the first frame wraps
     to the last; not before the page has loaded */
  addEventListener("load", function () { arm(i + 1); arm(i - 1); });

  function show(n) {
    var t = i = want = (n + slides.length) % slides.length;
    arm(t);
    if (document.readyState === "complete") { arm(t + 1); arm(t - 1); }
    thumbs.forEach(function (b, k) {
      b.classList.toggle("on", k === t);
      b.setAttribute("aria-selected", k === t ? "true" : "false");
    });
    if (num) num.textContent = t + 1;
    /* a thumbnail can jump to a frame not yet downloaded: keep the current
       one up until it is in, unless a later click has moved on */
    var im = slides[t] && slides[t].querySelector("img");
    bgsWhenLoaded(im, function () {
      if (want !== t) return;
      slides.forEach(function (s, k) { s.classList.toggle("on", k === t); });
    });
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
});


/* ---------- PDP: keep the buy decision above the fold ----------------------
   The spec table is four rows that are all placeholders on most products, and
   it used to sit between the price and Add to bag. It is below the button now.
   The table and its rows ship hidden; a row shows once the PDP above has
   filled its value in, and the table only if one has, so there are no rows
   saying "not set" and no labels with nothing beside them.
--------------------------------------------------------------------------- */
bgsRun(function () {
  "use strict";
  var specs = document.querySelector("[data-specs]");
  if (!specs) return;
  var rows = [].slice.call(specs.querySelectorAll("div"));
  var withValue = rows.filter(function (r) {
    var v = r.lastElementChild;
    return v && !v.querySelector(".slot") && v.textContent.trim() !== "";
  });
  specs.hidden = withValue.length === 0;
  rows.forEach(function (r) { r.hidden = withValue.indexOf(r) < 0; });
});


/* ---------- size chips pick a variant ---------------------------------------
   The chips carry a price, so choosing one has to move the price and the
   button with it. On a product card the whole tile is a link, so the click has
   to be stopped before it navigates.
--------------------------------------------------------------------------- */
bgsRun(function () {
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
});


/* ---------- collection: a real filter engine -------------------------------
   The collection page shipped a hardcoded oud-oils grid, so every category
   link relabelled the heading and still showed the same 11 products. This
   filters the real catalogue. Only facets the content layer carries are
   offered: category and price for all products, gender for the sprays. State
   lives in the URL so a filtered view is shareable.
--------------------------------------------------------------------------- */
bgsRun(function () {
  "use strict";
  var grid = document.querySelector("[data-grid]");
  if (!grid) return;
  var CAT = window.BGS_CATALOGUE || {};

  /* Each category's label, breadcrumb name and intro, and the same for "all"
     (the unfiltered page), come from content: build.py writes them into
     catalogue.js as BGS_CATS and prints the same text in the page. The keys
     are fixed in code; an unknown one reads as undefined, as it always has. */
  var CATS = window.BGS_CATS || {};
  function catText(key, part) { return (CATS[key] || {})[part]; }

  function params() {
    var q = new URLSearchParams(location.search),
        st = { cat: [], price: [], gender: [], ready: false, sort: "featured", q: "" };
    ["cat", "price", "gender"].forEach(function (k) {
      var v = q.get(k); if (v) st[k] = v.split(",").filter(Boolean);
    });
    if (q.get("ready") === "1") st.ready = true;
    if (q.get("sort")) st.sort = q.get("sort");
    if (q.get("q")) st.q = q.get("q").trim();
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
  var SKIP = ["a", "an", "and", "for", "in", "of", "the", "to", "with"];
  function match(pr, st) {
    if (st.cat.length && st.cat.indexOf(pr.cat) < 0) return false;
    if (st.gender.length && (!pr.gender || st.gender.indexOf(pr.gender) < 0)) return false;
    if (st.price.length && !st.price.some(function (b) { return inBand(pr.pn, b); })) return false;
    if (st.ready && !(pr.stock > 0)) return false;
    if (st.q) {
      /* every word must start a word in the name, category or notes, so
         "her" finds Her and Hers but not leatHER; a plural also matches its
         singular ("ouds", "lilies"), and "for", "the" and the like are not
         required, so "for her" works */
      var words = [pr.name, pr.crumb, pr.meta, pr.top, pr.heart, pr.base].join(" ")
        .toLowerCase().split(/[^a-z0-9؀-ۿ]+/);
      var starts = function (w) { return words.some(function (x) { return x.indexOf(w) === 0; }); };
      var has = function (w) {
        return starts(w) || (w.length > 3 && (
          (/ies$/.test(w) && starts(w.slice(0, -3) + "y")) ||
          (/es$/.test(w) && starts(w.slice(0, -2))) ||
          (/s$/.test(w) && starts(w.slice(0, -1)))));
      };
      var ask = st.q.toLowerCase().split(/[^a-z0-9؀-ۿ]+/).filter(Boolean);
      var need = ask.filter(function (w) { return SKIP.indexOf(w) < 0; });
      if (!(need.length ? need : ask).every(has)) return false;
    }
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
    var set = function (n) { return bgsImg(n, "-card-360") + " 360w, " + bgsImg(n, "-card") + " 520w"; };
    var o = '<img class="ph-a" src="' + bgsImg(imgs[0], "-card") + '" srcset="' + set(imgs[0]) +
            '" sizes="' + BGS_CARD_SIZES + '" alt="' + esc(pr.name) +
            '" loading="lazy" decoding="async" width="520" height="520">';
    if (imgs.length > 1)   /* hover-only: loads on the first pointer or focus */
      o += '<img class="ph-b" data-src="' + bgsImg(imgs[1], "-card") + '" data-srcset="' + set(imgs[1]) +
           '" sizes="' + BGS_CARD_SIZES + '" alt="" aria-hidden="true" decoding="async" width="520" height="520">';
    return o;
  }
  function cardHTML(key, pr) {
    var badge = pr.halo ? '<span class="badge res">Reserve</span>'
              : (pr.stock > 0 && pr.stock <= bgsRule("low_stock_at", 5)) ? '<span class="badge low">' + pr.stock + ' left</span>' : '';
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
      '<button type="button" class="btn sm solid" data-add="' + key + '" style="margin-top:4px">Add to bag</button></div></a>';
  }
  function pillsFor(st) {
    var out = [];
    st.cat.forEach(function (c) { out.push(["cat", c, catText(c, "label") || c]); });
    st.gender.forEach(function (g) { out.push(["gender", g, bgsCopy("collection.genders." + g, g)]); });
    st.price.forEach(function (b) { var p = b.split("-");
      out.push(["price", b, +p[1] > 99998 ? "AED " + p[0] + "+" : "AED " + p[0] + " to " + p[1]]); });
    if (st.q) out.push(["q", st.q, '"' + st.q + '"']);
    return out;
  }
  function render() {
    var st = params();
    /* the boxes mirror the search in force, cleared when it is removed; the
       one being typed in is left alone */
    document.querySelectorAll('form.search input[name="q"]').forEach(function (i) {
      if (document.activeElement !== i) i.value = st.q || "";
    });
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
    var title = catText(one || "all", "label");
    var t = document.querySelector("[data-title]"), intro = document.querySelector("[data-intro]"),
        cr = document.querySelector("[data-crumb]");
    if (t) t.textContent = title;
    if (intro) intro.textContent = catText(one || "all", "intro");
    if (cr) cr.textContent = bgsCopy("crumb_home", "Home") + " / " +
      (one ? bgsCopy("collection.crumb_categories", "Categories") + " / " : "") + catText(one || "all", "crumb");
    document.title = title + bgsTitleSuffix();

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
});


/* ---------- wishlist hearts, on every page ---------------------------------
   The heart sits inside the card's own link, so its handler must stop the
   click reaching the anchor. State is per browser; there is no account yet.
--------------------------------------------------------------------------- */
bgsRun(function () {
  "use strict";
  function get() {
    try {
      var v = JSON.parse(localStorage.getItem("bgs_wish") || "[]");
      return Array.isArray(v) ? v.filter(function (k) { return typeof k === "string"; }) : [];
    } catch (e) { return []; }
  }
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
  addEventListener("storage", function (e) { if (e.key === "bgs_wish" || e.key === null) sync(); });
  sync();
});


/* ---------- PDP tabs: five spans that could not be switched ---------- */
bgsRun(function () {
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
  /* the tab the address asks for, else the one marked on, else the first:
     the PDP takes out tabs that do not apply to the product, the marked one
     among them on bakhoor and gift sets */
  var want = new URLSearchParams(location.search).get("tab");
  var first = [].filter.call(tabs, function (t) { return t.getAttribute("data-tab") === want; })[0] ||
              document.querySelector("[data-tab].on") || tabs[0];
  show(first.getAttribute("data-tab"));
  tabs.forEach(function (t) {
    t.addEventListener("click", function () { show(t.getAttribute("data-tab")); });
    t.addEventListener("keydown", function (e) {
      var list = [].slice.call(tabs), i = list.indexOf(t);
      if (e.key === "ArrowRight") { e.preventDefault(); var nx = list[(i + 1) % list.length]; nx.focus(); nx.click(); }
      if (e.key === "ArrowLeft")  { e.preventDefault(); var pv = list[(i - 1 + list.length) % list.length]; pv.focus(); pv.click(); }
    });
  });
});


/* ---------- checkout: selectable payment method ---------- */
bgsRun(function () {
  "use strict";
  var pick = document.querySelector("[data-paypick]");
  if (!pick) return;
  pick.addEventListener("click", function (e) {
    var b = e.target.closest("button");
    if (!b) return;
    pick.querySelectorAll("button").forEach(function (x) { x.classList.remove("on"); });
    b.classList.add("on");
  });
});


/* ---------- SEO: keep faceted collection URLs out of the index -------------
   The filter engine applies ?cat=&price=&gender=… client-side; the brief
   (§14.4) wants those multi-facet combinations noindex,follow with a canonical
   to the clean collection page, to prevent crawl explosion.
--------------------------------------------------------------------------- */
bgsRun(function () {
  "use strict";
  if (!/collection\.html$/.test(location.pathname)) return;
  if (!location.search) return;
  var m = document.createElement("meta");
  m.name = "robots"; m.content = "noindex,follow";
  document.head.appendChild(m);
});


/* ---------- track order + corporate enquiry (front-end only) ----------------
   There is no backend, and these say so rather than pretending. Find-my-order
   validates the number and reveals the standard status sequence; the corporate
   form validates an email and acknowledges the enquiry. Their replies are
   content (BGS_COPY.track and .corporate); the email check stays here.
--------------------------------------------------------------------------- */
bgsRun(function () {
  "use strict";
  var find = document.querySelector("[data-findorder]");
  if (find) {
    find.addEventListener("click", function () {
      var num = (document.querySelector("[data-ordernum]") || {}).value || "";
      var phone = (document.querySelector("[data-orderphone]") || {}).value || "";
      var out = document.querySelector("[data-findresult]");
      out.hidden = false;
      if (!num.trim() && !phone.trim()) {
        out.textContent = bgsCopy("track.replies.missing", "Enter your order number, or the phone you ordered with.");
        return;
      }
      out.textContent = bgsFill(bgsCopy("track.replies.looking", "Looking for {query}. Live courier tracking connects with the backend; the stages below are the standard sequence your order moves through."),
                                { query: num.trim() || phone.trim() });
    });
  }
  var send = document.querySelector("[data-cqsend]");
  if (send) {
    send.addEventListener("click", function () {
      var g = function (k) { var e = document.querySelector('[data-cq="' + k + '"]'); return e ? e.value.trim() : ""; };
      var out = document.querySelector("[data-cqresult]");
      out.hidden = false;
      var email = g("email");
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
        out.textContent = bgsCopy("corporate.replies.invalid_email", "Enter a valid work email so we can reply.");
        return;
      }
      var name = g("name"), units = g("units");
      out.textContent =
        (name ? bgsFill(bgsCopy("corporate.replies.thanks_name", "Thank you, {name}"), { name: name })
              : bgsCopy("corporate.replies.thanks", "Thank you")) + ". " +
        (units ? bgsFill(bgsCopy("corporate.replies.quote_units", "We will come back with a quote for {n} units"), { n: units })
               : bgsCopy("corporate.replies.quote", "We will come back with a quote")) + ". " +
        bgsCopy("corporate.replies.not_sent", "This form is front-end only for now; the enquiry is not yet sent anywhere.");
    });
  }
});
/* ---------- gift box builder ----------------------------------------------
   Was a static mock: two inert "3 slots / 6 slots" pills, three hardcoded
   slots and a total that never moved. The picker cards below it are ordinary
   product links, so adding has to intercept the click the same way the
   wishlist heart does.
--------------------------------------------------------------------------- */
bgsRun(function () {
  "use strict";
  var slotsHost = document.querySelector("[data-slots]");
  if (!slotsHost) return;
  var CAT = window.BGS_CATALOGUE || {};
  var BOX_FEE = bgsRule("giftbox_fee", 25);
  var BOX_AT = bgsRule("giftbox_volume_discount_at", 3), BOX_PCT = bgsRule("giftbox_volume_discount_percent", 10);
  var size = 3, picked = [];
  /* the slots' words, from pages.json (BGS_COPY.gift_box), escaped for the
     slot markup below */
  var T = {
    filled: bgsCopyHtml("gift_box.slots.filled", "Slot {n}"), remove: bgsCopyHtml("gift_box.slots.remove", "tap to remove"),
    empty: bgsCopyHtml("gift_box.slots.empty", "Slot {n} empty"), choose: bgsCopyHtml("gift_box.slots.choose", "Choose a scent"),
    pick: bgsCopyHtml("gift_box.slots.pick", "Pick from below")
  };

  function priceOf(k) { var p = bgsProduct(k); return (p && p.pn) || 0; }

  function renderSlots() {
    var html = "";
    for (var i = 0; i < size; i++) {
      var k = picked[i], slotNo = { n: i + 1 };
      if (k) {
        html += '<button type="button" class="p slot-filled" data-unpick="' + i + '">' +
          '<div class="ph"><span class="none">' + bgsFill(T.filled, slotNo) + "</span></div>" +
          '<div class="b"><span class="nm">' + CAT[k].name + "</span>" +
          '<span class="notes">AED ' + CAT[k].price + " &middot; " + T.remove + "</span></div></button>";
      } else {
        html += '<div class="p" style="border-style:dashed"><div class="ph" style="background:var(--alt)">' +
          '<span class="none">' + bgsFill(T.empty, slotNo) + "</span></div>" +
          '<div class="b"><span class="nm" style="color:var(--faint)">' + T.choose + "</span>" +
          '<span class="notes">' + T.pick + "</span></div></div>";
      }
    }
    slotsHost.innerHTML = html;
    slotsHost.className = "grid " + (size === 6 ? "g3" : "g3");
  }

  function renderSummary() {
    var n = picked.length;
    var scents = picked.reduce(function (t, k) { return t + priceOf(k); }, 0);
    var disc = n >= BOX_AT ? Math.round(scents * (BOX_PCT / 100)) : 0;
    var total = scents + BOX_FEE - disc;

    var q = function (s) { return document.querySelector(s); };
    q("[data-boxn]").textContent = bgsFill(n === 1 ? bgsCopy("gift_box.summary.scents_one", "{n} scent")
                                                   : bgsCopy("gift_box.summary.scents_many", "{n} scents"), { n: n });
    q("[data-boxscents]").textContent = "AED " + scents;
    var dr = q("[data-boxdisc]");
    dr.style.color = n >= BOX_AT ? "var(--green)" : "var(--faint)";
    dr.querySelector("span:last-child").innerHTML = n >= BOX_AT ? "&minus;AED " + disc : "&minus;" + BOX_PCT + "%";
    q("[data-boxtotal]").textContent = "AED " + total;

    var cta = q("[data-boxcta]"), left = size - n;
    if (left > 0) {
      cta.textContent = bgsFill(left === 1 ? bgsCopy("gift_box.summary.fill_one", "Fill {n} more slot")
                                           : bgsCopy("gift_box.summary.fill_many", "Fill {n} more slots"), { n: left });
      cta.classList.add("ghost"); cta.classList.remove("solid");
    } else {
      cta.textContent = bgsFill(bgsCopy("gift_box.summary.add", "Add box to bag: {total}"), { total: "AED " + total });
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
    /* the card's heart and size chips have their own handlers */
    if (card && card.getAttribute("href") && !e.target.closest("[data-wish], [data-size]")) {
      var key = new URLSearchParams(card.getAttribute("href").split("?")[1] || "").get("p");
      if (!bgsProduct(key)) return;
      /* Immediate: the bag's own click listener is on document too, and a
         card's Add to bag would otherwise fill a slot and add to the bag */
      e.preventDefault(); e.stopImmediatePropagation();
      if (picked.length >= size) {
        var cta = document.querySelector("[data-boxcta]");
        cta.textContent = bgsCopy("gift_box.summary.full", "Box is full, remove one first");
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
});


/* ---------- cart: real state, in localStorage ------------------------------
   Replaces the four demo lines that used to be baked into cart.html at build
   time. Stored as [{id, qty}]; the gift line is derived from the subtotal at
   render time rather than stored, so it cannot be edited or orphaned.
--------------------------------------------------------------------------- */
bgsRun(function () {
  "use strict";

  var KEY = "bgs_cart";
  var GIFT_AT = bgsRule("gift_with_purchase.threshold", 300);
  var GIFT_LABEL = bgsRule("gift_with_purchase.label", "Mystery oud, 3 ml");

  function read() {
    try {
      var v = JSON.parse(localStorage.getItem(KEY) || "[]");
      /* storage can hold anything, so quantities get the same 1 to 20 clamp
         that add() applies: negative, fractional, text or missing become sane */
      return Array.isArray(v) ? v.filter(function (l) { return l && typeof l.id === "string"; })
        .map(function (l) { return { id: l.id, qty: Math.max(1, Math.min(20, Math.floor(Number(l.qty)) || 1)) }; }) : [];
    } catch (e) { return []; }
  }
  function write(lines) {
    try { localStorage.setItem(KEY, JSON.stringify(lines)); } catch (e) {}
    paintCount();
    render();
  }
  function cat(id) {
    return bgsProduct(id);
  }
  function units() {
    return read().reduce(function (n, l) { return n + (cat(l.id) ? l.qty : 0); }, 0);
  }

  function add(id, qty) {
    if (!id || !cat(id)) return false;
    var lines = read(), hit = null;
    lines.forEach(function (l) { if (l.id === id) hit = l; });
    if (hit) hit.qty = Math.min(20, (hit.qty || 1) + (qty || 1));
    else lines.push({ id: id, qty: Math.min(20, qty || 1) });
    write(lines);
    return true;
  }
  function setQty(id, qty) {
    var lines = read().map(function (l) {
      return l.id === id ? { id: id, qty: Math.max(1, Math.min(20, qty)) } : l;
    });
    write(lines);
  }
  function remove(id) {
    write(read().filter(function (l) { return l.id !== id; }));
  }

  /* the bag badge, on every page */
  function paintCount() {
    var n = units();
    document.querySelectorAll("[data-bagcount]").forEach(function (el) {
      el.textContent = n;
      el.hidden = n === 0;
    });
    var label = document.querySelector("[data-bagitems]");
    if (label) label.textContent = n ? " · " + bgsFill(n === 1 ? bgsCopy("cart.items.one", "{n} item")
                                                               : bgsCopy("cart.items.many", "{n} items"), { n: n }) : "";
  }

  function money(n) {
    return "AED " + n.toLocaleString("en-AE", { maximumFractionDigits: 2 });
  }

  /* catalogue text goes into the bag's markup as text, never as code */
  function escText(t) {
    return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;");
  }

  function lineHtml(l, p) {
    var halo = !!p.halo;
    var img = (p.images && p.images[0])
      ? '<img src="' + bgsImg(p.images[0], "-thumb") +
        '" alt="' + (p.name || "").replace(/"/g, "&quot;") + '" width="160" height="160">'
      : '<span class="none">' + bgsCopyHtml("cart.line.no_image", "Image") + "</span>";
    return '<div class="line" data-line data-id="' + l.id + '" data-unit="' + p.pn +
      '" data-halo="' + (halo ? "1" : "0") + '" data-gift="0">' +
      '<a class="im" href="product.html?p=' + l.id + '">' + img + '</a>' +
      '<div class="linfo"><div class="lname">' + escText(p.name) + '</div>' +
      '<div class="lmeta">' + escText(p.meta || "") + '</div>' +
      '<span class="stepper" data-stepper>' +
        '<button type="button" data-step="-1" aria-label="Decrease quantity">&minus;</button>' +
        '<i data-qty>' + l.qty + '</i>' +
        '<button type="button" data-step="1" aria-label="Increase quantity">+</button></span>' +
      (halo ? '<div class="norm" style="margin-top:6px">Never discounted</div>' : "") +
      '<button type="button" class="lrem" data-remove="' + l.id + '">' + bgsCopyHtml("cart.line.remove", "Remove") + "</button>" +
      '</div>' +
      '<div class="lprice"><span data-lineprice>' + money(p.pn * l.qty) + '</span></div></div>';
  }

  function giftHtml() {
    return '<div class="line" data-line data-unit="0" data-halo="0" data-gift="1">' +
      '<div class="im"><span class="none">' + bgsCopyHtml("cart.gift_line.placeholder", "Gift") + "</span></div>" +
      '<div class="linfo"><div class="lname">' + GIFT_LABEL.replace(/&/g, "&amp;").replace(/</g, "&lt;") + '</div>' +
      '<div class="lmeta">' + bgsFill(bgsCopyHtml("cart.gift_line.meta", "Gift with purchase over {amount}"), { amount: money(GIFT_AT) }) +
      "</div></div>" +
      '<div class="lprice"><span data-lineprice>' + bgsCopyHtml("cart.summary.free", "Free") + "</span></div></div>";
  }

  function render() {
    var host = document.querySelector("[data-cartlines]");
    if (!host) return;                       // not the cart page

    var lines = read().filter(function (l) { return cat(l.id); });
    var sub = lines.reduce(function (n, l) { return n + cat(l.id).pn * l.qty; }, 0);

    host.innerHTML = lines.map(function (l) { return lineHtml(l, cat(l.id)); }).join("") +
      (sub >= GIFT_AT ? giftHtml() : "");

    var empty = lines.length === 0;
    var toggle = function (sel, hide) {
      var el = document.querySelector(sel);
      if (el) el.hidden = hide;
    };
    toggle("[data-cartempty]", !empty);
    toggle("[data-cartsummary]", empty);
    toggle("[data-cartprogress]", empty);
    toggle("[data-cartnote]", empty || !lines.some(function (l) {
      var p = cat(l.id);
      return p && !!p.halo;
    }));

    if (typeof window.BGS_RECALC === "function") window.BGS_RECALC();
    /* the bag page's checkout bar copies the total recalc has just written */
    document.dispatchEvent(new CustomEvent("bgs:bagchange"));
  }

  /* The bag as it is now, for the added-to-bag panel: the lines whose product
     the catalogue still has, with read()'s 1 to 20 clamp, and the bag lines'
     own money format, so the panel cannot disagree with cart.html. */
  window.BGS_BAG = {
    lines: function () { return read().filter(function (l) { return cat(l.id); }); },
    money: money
  };

  /* add to bag, from anywhere */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-add]");
    if (btn) {
      e.preventDefault();
      e.stopPropagation();                   // cards are wrapped in a link
      var id = btn.getAttribute("data-add");
      if (!id) {                             // PDP: the product in the URL
        id = new URLSearchParams(location.search).get("p");
      }
      var qty = 1;
      if (btn.hasAttribute("data-addqty")) {
        var q = document.querySelector("[data-stepper] [data-qty]");
        qty = q ? parseInt(q.textContent, 10) || 1 : 1;
      }
      if (add(id, qty)) {
        /* The label to go back to is kept from the first press only: a
           second press inside the 1.2 s used to save "Added" as it, for good. */
        if (!btn.hasAttribute("data-was")) btn.setAttribute("data-was", btn.textContent);
        btn.textContent = bgsAr(bgsCopy("cart.added.button", "Added"));
        clearTimeout(btn._bgsT);
        btn._bgsT = setTimeout(function () {
          btn.textContent = btn.getAttribute("data-was");
          btn.removeAttribute("data-was");
        }, 1200);
        /* the added-to-bag panel listens in a block of its own: an error in
           a listener stays there, and the add above has already happened */
        document.dispatchEvent(new CustomEvent("bgs:added", { detail: { id: id, trigger: btn } }));
      }
      return;
    }

    var rem = e.target.closest("[data-remove]");
    if (rem) {
      e.preventDefault();
      remove(rem.getAttribute("data-remove"));
    }
  });

  /* quantity steppers on the cart page write through to storage */
  document.addEventListener("click", function (e) {
    var step = e.target.closest("[data-line] [data-step]");
    if (!step) return;
    var line = step.closest("[data-line]");
    var id = line && line.getAttribute("data-id");
    if (!id) return;
    var cur = parseInt(line.querySelector("[data-qty]").textContent, 10) || 1;
    setQty(id, cur + (parseInt(step.dataset.step, 10) || 0));
  }, true);

  /* another tab changed the bag: repaint, so this one cannot write back a
     stale copy over it */
  addEventListener("storage", function (e) { if (e.key === KEY || e.key === null) { paintCount(); render(); } });

  paintCount();
  render();
});

/* ---------- added to bag: one panel after every Add -------------------------
   An Add used to turn its button into "Added" for a moment and bump the
   masthead count, which a phone has usually scrolled out of sight, and
   nothing led on to the bag or to checkout. Every Add now opens this panel:
   the product as the bag holds it (picture, name, size line, quantity and
   line price), the bag's count and subtotal, View bag and Checkout. It is
   filled from the bag after the add, with the bag page's own sums, so it
   cannot disagree with cart.html. It names no size chip, because the bag
   keeps none yet and charges the default (HANDOFF, open decision 15).

   Up to 900px it is a sheet resting on the tab bar; wider, a card under the
   masthead's bag, or under the category bar once the masthead has scrolled
   away. There is one panel: an Add while it is open refreshes it. It never
   takes focus and never closes on a timer, since it holds actions (WCAG
   2.2.1): its cross, Escape, a click or tap anywhere else, or leaving the
   page close it, and scrolling leaves it be. Tab from the pressed button
   goes into it, and Tab from its cross goes on to what followed the button.
   A screen reader hears it through a polite live region.

   The bag's add handler announces an add with "bgs:added", so an error in
   here cannot stop one. The gift box stops its cards' clicks before that
   handler runs, so picking a slot opens nothing. */
bgsRun(function () {
  "use strict";
  var BAG = window.BGS_BAG;
  if (!BAG || document.querySelector("[data-cartlines]")) return;   // the bag page has no Add
  var el = null, live = null, trigger = null, hideT = null, liveT = null;
  var BAGLINK = '.mast a.act[href="cart.html"]';
  var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), ' +
                  'select:not([disabled]), textarea:not([disabled]), [tabindex]';
  function q(s) { return el.querySelector(s); }
  function isOpen() { return !!el && !el.hidden && el.classList.contains("on"); }

  function build() {
    if (el) return;
    el = document.createElement("section");
    el.className = "added";
    el.id = "bgs-added";
    el.setAttribute("aria-labelledby", "bgs-added-h");
    el.hidden = true;
    /* fixed markup only: every word and all catalogue text go in with
       textContent, in fill(). The order makes Tab run View bag, Checkout,
       then the cross. */
    el.innerHTML =
      '<p class="added-hd" id="bgs-added-h"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M5 12.5l4.5 4.5L19 7.5"/></svg><span data-at></span></p>' +
      '<div class="added-p"><a class="added-im" tabindex="-1" aria-hidden="true" href="product.html"></a>' +
      '<div class="added-t"><span class="added-nm"></span><span class="added-meta"></span>' +
      '<span class="added-q"></span></div><b class="added-pr"></b></div>' +
      '<div class="added-s"><span></span><b></b></div>' +
      '<div class="added-b"><a class="btn" href="cart.html"></a><a class="btn solid" href="checkout.html"></a></div>' +
      '<button type="button" class="added-x"><span aria-hidden="true">&times;</span></button>';
    live = document.createElement("div");
    live.className = "none-visual";
    live.setAttribute("role", "status");
    live.setAttribute("aria-live", "polite");
    live.setAttribute("aria-atomic", "true");
    live.setAttribute("data-addedlive", "");
    document.body.appendChild(el);
    document.body.appendChild(live);
    q(".added-x").addEventListener("click", function () { hide(); });
  }

  /* Everything from the bag after the add: n is how many of this product
     it holds now (a second press reads Qty 2), and the line price and the
     subtotal are the bag lines' pn times quantity. Returns the sentence the
     live region reads. */
  function fill(id, p) {
    var n = 0, units = 0, sub = 0;
    BAG.lines().forEach(function (l) {
      units += l.qty;
      sub += bgsProduct(l.id).pn * l.qty;
      if (l.id === id) n = l.qty;
    });
    var title = bgsAr(bgsCopy("cart.added.title", "Added to your bag"));
    var qty = bgsFill(bgsAr(bgsCopy("cart.added.qty", "Qty {n}")), { n: n });
    var subLabel = bgsAr(bgsCopy("cart.summary.subtotal", "Subtotal"));
    var count = bgsFill(bgsAr(units === 1 ? bgsCopy("cart.items.one", "{n} item")
                                          : bgsCopy("cart.items.many", "{n} items")), { n: units });
    q("[data-at]").textContent = title;
    var im = q(".added-im");
    im.setAttribute("href", "product.html?p=" + encodeURIComponent(id));
    im.textContent = "";
    if (p.images && p.images[0]) {
      var img = document.createElement("img");
      img.alt = "";
      img.width = 160;
      img.height = 160;
      img.src = bgsImg(p.images[0], "-thumb");
      im.appendChild(img);
    } else {
      var none = document.createElement("span");
      none.className = "none";
      none.textContent = bgsAr(bgsCopy("cart.line.no_image", "Image"));
      im.appendChild(none);
    }
    q(".added-nm").textContent = p.name;
    q(".added-meta").textContent = p.meta || "";
    q(".added-q").textContent = qty;
    q(".added-pr").textContent = BAG.money(p.pn * n);
    q(".added-s span").textContent = subLabel + " · " + count;
    q(".added-s b").textContent = BAG.money(sub);
    q(".added-b .btn:not(.solid)").textContent = bgsAr(bgsCopy("cart.added.view_bag", "View bag"));
    q(".added-b .btn.solid").textContent = bgsAr(bgsCopy("cart.summary.checkout", "Checkout"));
    q(".added-x").setAttribute("aria-label", bgsAr(bgsCopy("cart.added.close", "Close")));
    return title + ": " + p.name + ", " + qty + ". " + subLabel + " " + BAG.money(sub) + ", " + count + ".";
  }

  /* Up to 900px the sheet is all CSS. Wider, the card hangs 12px under the
     masthead's bag, its end edge in line with the bag's and its caret at
     the bag icon; once the masthead has scrolled away, under the category
     bar without the caret. A card taller than the room left scrolls. */
  function place() {
    var s = el.style;
    s.top = s.left = s.right = s.maxHeight = s.overflowY = "";
    s.removeProperty("--caret");
    el.classList.remove("anchored");
    if (matchMedia("(max-width:900px)").matches) return;
    var rtl = getComputedStyle(el).direction === "rtl";
    var bag = document.querySelector(BAGLINK);
    var r = bag && bag.getBoundingClientRect();
    var shown = !!r && (r.width > 0 || r.height > 0);
    var end = shown ? Math.max(16, Math.round(rtl ? r.left : document.documentElement.clientWidth - r.right)) : 16;
    var top;
    if (shown && r.bottom > 0) {
      top = r.bottom + 12;
      el.classList.add("anchored");
    } else {
      var nav = document.querySelector(".catnav");
      top = (nav ? Math.max(0, nav.getBoundingClientRect().bottom) : 0) + 12;
    }
    top = Math.round(top);
    s.top = top + "px";
    s[rtl ? "left" : "right"] = end + "px";
    if (el.classList.contains("anchored")) {
      var ir = (bag.querySelector("svg") || bag).getBoundingClientRect(), mid = ir.left + ir.width / 2;
      var box = el.getBoundingClientRect();
      var caret = rtl ? mid - box.left - 6 : box.right - mid - 6;
      s.setProperty("--caret", Math.round(Math.max(12, Math.min(box.width - 24, caret))) + "px");
    }
    var room = innerHeight - top - 12;
    if (el.offsetHeight > room) {
      s.maxHeight = Math.max(120, Math.floor(room)) + "px";
      s.overflowY = "auto";
      el.classList.remove("anchored");
    }
  }

  function say(msg) {
    clearTimeout(liveT);
    live.textContent = "";
    liveT = setTimeout(function () { live.textContent = msg; }, 120);
  }

  function show(d) {
    var id = d && d.id, p = bgsProduct(id);
    if (!p) return;
    build();
    var msg = fill(id, p);
    trigger = d.trigger || null;
    clearTimeout(hideT);
    if (el.hidden) {
      el.hidden = false;
      place();
      void el.offsetWidth;                 // one layout read, so the entrance runs from its start
    } else {
      place();                             // open already: refreshed, no second entrance
    }
    el.classList.add("on");
    say(msg);
  }

  /* now: straight away, for pagehide. Focus inside the panel goes back to
     the pressed button, or to the masthead's bag if that button is gone
     (the collection redraws its cards on every filter change). */
  function hide(now) {
    if (!el || el.hidden) return;
    var inside = el.contains(document.activeElement);
    el.classList.remove("on");
    clearTimeout(hideT);
    if (now || matchMedia("(prefers-reduced-motion: reduce)").matches) el.hidden = true;
    else hideT = setTimeout(function () { el.hidden = true; }, 220);
    if (inside && !now) {
      var back = trigger && document.contains(trigger) ? trigger : document.querySelector(BAGLINK);
      if (back) back.focus();
    }
  }

  /* the first visible control after the pressed button, outside the panel */
  function nextAfter(t) {
    if (!t || !document.contains(t)) return null;
    var all = document.querySelectorAll(FOCUSABLE);
    for (var i = 0; i < all.length; i++) {
      var n = all[i];
      if (n.tabIndex < 0 || el.contains(n) || !(t.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
      var r = n.getBoundingClientRect();
      if ((r.width > 0 || r.height > 0) && getComputedStyle(n).visibility !== "hidden") return n;
    }
    return null;
  }

  document.addEventListener("bgs:added", function (e) { show(e.detail); });

  /* Capture: the bag's add handler stops the click and the gift box's stops
     it outright, so a listener on the way back up would miss both. An Add
     is let through, so the next one refreshes the panel instead of closing
     and reopening it. The language toggle counts as outside. */
  document.addEventListener("click", function (e) {
    if (!isOpen()) return;
    var t = e.target;
    if (el.contains(t) || (t.closest && t.closest("[data-add]"))) return;
    hide();
  }, true);

  /* no trap: Escape closes, and three Tab hand-offs join the panel to the
     button that opened it; every other key is the browser's own */
  document.addEventListener("keydown", function (e) {
    if (!isOpen()) return;
    if (e.key === "Escape" || e.key === "Esc") { hide(); return; }
    if (e.key !== "Tab" || e.altKey || e.ctrlKey || e.metaKey) return;
    var a = document.activeElement, first = q(".added-b .btn"), there = trigger && document.contains(trigger);
    if (!e.shiftKey && there && a === trigger) {
      e.preventDefault(); first.focus();
    } else if (e.shiftKey && there && a === first) {
      e.preventDefault(); trigger.focus();
    } else if (!e.shiftKey && a === q(".added-x")) {
      var n = nextAfter(trigger);
      if (n) { e.preventDefault(); n.focus(); }
    }
  });

  addEventListener("resize", function () { if (isOpen()) place(); });
  /* a page restored from the back/forward cache opens without it */
  addEventListener("pagehide", function () { hide(true); });
});

/* ---------- bag page: checkout bar on phones and short screens --------------
   On a phone the summary, and its Checkout, sits under the progress bars and
   the lines: below the fold with a single line on every phone, on a landscape
   phone, and with a full bag on a portrait tablet. This bar holds the total
   and a Checkout while that button is not fully in sight above the tab bar,
   and steps aside once it is, so one Checkout is on screen at a time. It is
   back once the summary has scrolled up out of sight, so the foot of the page
   has a way to checkout too. The total is the summary's own text, copied
   after each recalc: there is no second sum.

   An IntersectionObserver, which the product page's sticky bar gave up on
   (its note above), so with that bar's lessons: the first state is measured
   outright, the observer is rebuilt when the window or the breakpoint
   changes, and it reports at 0, 0.5 and 1, which a jumped scroll still
   crosses. Without an observer the bar stays hidden and the summary's own
   button is the way through. */
bgsRun(function () {
  "use strict";
  var bar = document.querySelector("[data-bagbar]");
  var link = document.querySelector("[data-checkout]");
  var summary = document.querySelector("[data-cartsummary]");
  if (!bar || !link || !summary || !("IntersectionObserver" in window)) return;
  var total = bar.querySelector("[data-bagbartotal]");
  var mq = matchMedia("(max-width:900px), (max-height:500px)");
  var io = null, seen = false, t = null;

  /* the tab bar is only there up to 900px; the fold stops at its top */
  function tabH() {
    var tb = document.querySelector(".tabbar");
    return tb && getComputedStyle(tb).display !== "none" ? Math.round(tb.getBoundingClientRect().height) : 0;
  }

  /* an empty bag hides the summary, and recalc stops before the total then,
     so the bar goes with it rather than show a stale amount */
  function sync() {
    var src = document.querySelector("[data-total]");
    if (src) total.textContent = src.textContent;
    var on = mq.matches && !summary.hidden && !seen;
    if (bar.classList.contains("on") !== on) {
      bar.classList.toggle("on", on);
      bar.setAttribute("aria-hidden", on ? "false" : "true");
    }
  }

  function watch() {
    if (io) io.disconnect();
    var h = tabH(), r = link.getBoundingClientRect();
    seen = r.height > 0 && r.top >= 0 && r.bottom <= innerHeight - h;
    io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { seen = e.isIntersecting && e.intersectionRatio > 0.98; });
      sync();
    }, { threshold: [0, 0.5, 1], rootMargin: "0px 0px -" + h + "px 0px" });
    io.observe(link);
    sync();
  }

  addEventListener("resize", function () { clearTimeout(t); t = setTimeout(watch, 150); });
  if (mq.addEventListener) mq.addEventListener("change", watch);
  else if (mq.addListener) mq.addListener(watch);
  /* a quantity change, a remove, or the bag changed in another tab */
  document.addEventListener("bgs:bagchange", sync);
  watch();
});

/* ---------- share the product ----------------------------------------------
   navigator.share opens the phone's own share sheet, which on this traffic
   means WhatsApp and iMessage without us building either. It needs a secure
   context and is mostly mobile, so the desktop path copies the link instead
   and the button says so.

   The URL is rebuilt from ?p= rather than taken from location.href, so a
   shared link carries the product and nothing else - not a filter the sharer
   happened to have set. */
bgsRun(function () {
  "use strict";
  var btn = document.querySelector("[data-share]");
  if (!btn) return;

  var label = btn.querySelector("[data-sharelabel]");
  var reset = null;
  var SHARE = bgsCopy("product.share.label", "Share"), COPIED = bgsCopy("product.share.copied", "Link copied"),
      FAILED = bgsCopy("product.share.failed", "Could not copy");

  function say(text, ok) {
    label.textContent = text;
    btn.classList.toggle("done", ok);
    clearTimeout(reset);
    reset = setTimeout(function () {
      label.textContent = SHARE;
      btn.classList.remove("done");
    }, 2200);
  }

  /* Whatever ?p= named, falling back to the page's own default heading. */
  function payload() {
    var key = new URLSearchParams(location.search).get("p");
    var pr = key ? (window.BGS_CATALOGUE || {})[key] : null;
    var h1 = document.querySelector(".buy h1");
    var name = (pr && pr.name) || (h1 && h1.textContent.trim()) || "BGS Corner";
    return {
      title: name + bgsTitleSuffix(),
      text: pr ? name + ", AED " + pr.price : name,
      url: location.origin + location.pathname +
           (key ? "?p=" + encodeURIComponent(key) : "")
    };
  }

  /* Only reports a copy the clipboard actually accepted. */
  function copy(url) {
    if (!navigator.clipboard) return say(FAILED, false);
    navigator.clipboard.writeText(url).then(
      function () { say(COPIED, true); },
      function () { say(FAILED, false); }
    );
  }

  btn.addEventListener("click", function () {
    var p = payload();
    if (!navigator.share) return copy(p.url);
    /* Dismissing the sheet is a choice, not a failure. */
    navigator.share(p).catch(function (err) {
      if (!err || err.name !== "AbortError") copy(p.url);
    });
  });
});

/* ---------- the sticky bar waits its turn -----------------------------------
   It used to sit on every product page from the first paint, covering 63px of
   the screen to show a second copy of the Add to bag that was directly
   underneath it - and pushing the real one out of view, which is how it came
   to render clipped.

   Now it appears only once the real button is not usable. "Usable" is the whole
   button inside the fold, and the fold stops at the tab bar, which is measured
   rather than assumed because it is only there on a phone.

   Two things this deliberately is not:

   An IntersectionObserver. One was tried and got the hand-off wrong twice, 600px
   late leaving the button and never re-hiding on the way back up, because a
   threshold only reports when it is crossed and a jumped scroll can skip it.

   rAF-throttled. Also tried. requestAnimationFrame does not run while the page
   is not being painted, so the bar could sit a whole scroll behind. The read is
   one getBoundingClientRect on a passive listener, which is cheap enough to do
   outright; the expensive part, measuring the tab bar, is cached and only
   redone when something could have moved it. The class is written only when the
   answer changes.

   If any of it fails the bar simply stays visible, which is the safe way to be
   wrong. */
bgsRun(function () {
  "use strict";
  var bar = document.querySelector(".stickybuy");
  var inline = document.querySelector(".atcrow [data-add]");
  if (!bar || !inline) return;

  var tabH = 0, last = null;

  function measureTab() {
    var tb = document.querySelector(".tabbar");
    tabH = tb && getComputedStyle(tb).display !== "none"
      ? tb.getBoundingClientRect().height : 0;
  }

  function sync() {
    var r = inline.getBoundingClientRect();
    var usable = r.top >= 0 && r.bottom <= window.innerHeight - tabH;
    if (usable === last) return;
    last = usable;
    bar.classList.toggle("hidden", usable);
  }

  function remeasure() { measureTab(); sync(); }

  measureTab();
  addEventListener("scroll", sync, { passive: true });
  addEventListener("resize", remeasure);
  /* a size chip rewrites the button label, which can change its height */
  document.addEventListener("click", remeasure);
  document.addEventListener("visibilitychange", remeasure);
  sync();
});

/* ---------- category bar: mark where you are --------------------------------
   The pages are static, so the build cannot know which category is open - it
   is in the query string. Matched on ?cat= where there is one, and on the file
   name for the three entries that are their own page (gift box, occasion,
   corporate), which is why data-catnav is empty on those. */
bgsRun(function () {
  "use strict";
  var links = document.querySelectorAll("[data-catnav]");
  if (!links.length) return;

  var cat = new URLSearchParams(location.search).get("cat") || "";
  var page = location.pathname.split("/").pop() || "index.html";

  /* First match only. Two entries once pointed at gift-box.html in
     navigation.json (Build Your Gift Box and Shop by Occasion), and a plain
     match lit both at once on that page. Two labels sharing one destination is a content question that
     is still open; until it is answered the bar should at least claim one
     place. */
  var claimed = false;
  links.forEach(function (a) {
    var href = a.getAttribute("href");
    var target = href.split("?")[0];
    var on = !claimed && (cat ? a.dataset.catnav === cat
                              : (target === page && !href.includes("?cat=")));
    if (on) claimed = true;
    a.classList.toggle("on", on);
    if (on) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
});

/* ---------- one card height for every slide ---------------------------------
   On a phone the copy card sits in the flow under the band, so its height is
   whatever that slide's copy needs: measured 183, 211, 183, 191 and 211, which
   made the hero grow and shrink 28px every time the carousel turned.

   The tallest is measured rather than written down, because a number would be
   wrong the first time someone edits a headline. Each card is shown for one
   synchronous read and put back, so nothing paints mid-measurement.

   Desktop is left alone: there the cards are absolutely positioned and already
   fill the hero. */
bgsRun(function () {
  "use strict";
  var hero = document.querySelector(".hero");
  var overs = hero && hero.querySelectorAll(".over");
  if (!overs || overs.length < 2) return;

  var phone = window.matchMedia("(max-width:900px)");

  function equalise() {
    overs.forEach(function (o) { o.style.minHeight = ""; });
    if (!phone.matches) return;

    var was = [], tallest = 0;
    overs.forEach(function (o) { was.push(o.classList.contains("on")); });
    overs.forEach(function (o) {
      o.classList.add("on");
      tallest = Math.max(tallest, o.getBoundingClientRect().height);
      o.classList.remove("on");
    });
    overs.forEach(function (o, i) {
      if (was[i]) o.classList.add("on");
      o.style.minHeight = tallest + "px";
    });
  }

  equalise();
  addEventListener("resize", equalise);
  if (phone.addEventListener) phone.addEventListener("change", equalise);
});

/* ---------- the hover photo on product cards -------------------------------
   A card's second photo only shows on hover or keyboard focus, so it is not
   requested until a pointer or focus first reaches the card. At opacity 0 with
   a src, every card near the viewport downloaded both photos. Touch screens
   never show it (flow.css), so a tap does not fetch it either.
--------------------------------------------------------------------------- */
bgsRun(function () {
  "use strict";
  /* asked on every hover, not once: a tablet can get a mouse after load */
  var touch = window.matchMedia ? matchMedia("(hover:none)") : null;
  function arm(e) {
    if (touch && touch.matches) return;
    var c = e.target.closest && e.target.closest(".p");
    var b = c && c.querySelector(".ph-b[data-src]");
    if (!b) return;
    b.srcset = b.getAttribute("data-srcset"); b.src = b.getAttribute("data-src");
    b.removeAttribute("data-src"); b.removeAttribute("data-srcset");
  }
  document.addEventListener("pointerover", arm, { passive: true });
  document.addEventListener("focusin", arm);
});

/* ---------- same-day cutoff in the header strip ----------------------------
   The strip used to say "3h 47m" on every page at every hour. The time left is
   now worked out in Dubai time (UTC+4, no daylight saving) and shown only
   before the same-day cutoff in settings; after it the rule stands alone.
--------------------------------------------------------------------------- */
bgsRun(function () {
  "use strict";
  var box = document.querySelector("[data-cutoff]");
  if (!box) return;
  var CUTOFF = bgsRule("sameday_cutoff_minutes", 14 * 60);
  function tick() {
    var d = new Date(), mins = ((d.getUTCHours() + 4) % 24) * 60 + d.getUTCMinutes(), left = CUTOFF - mins;
    box.hidden = left <= 0;
    if (left > 0) box.querySelector("b").textContent = Math.floor(left / 60) + "h " + (left % 60) + "m";
  }
  tick(); setInterval(tick, 30000);
});

/* ---------- product films on the homepage ----------------------------------
   Each card starts as a still. A film is requested only once its card is on
   screen, plays muted and looped while it stays there, and pauses when it
   leaves. With reduced motion or data saver on, the stills stay.
--------------------------------------------------------------------------- */
bgsRun(function () {
  "use strict";
  var films = document.querySelectorAll(".reel video[data-src]");
  if (!films.length || !("IntersectionObserver" in window)) return;
  var quiet = (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) ||
              (navigator.connection && navigator.connection.saveData);
  if (quiet) return;
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      var v = en.target;
      if (en.isIntersecting) {
        if (!v.getAttribute("src")) {
          v.muted = true;
          v.addEventListener("playing", function () { v.classList.add("on"); }, { once: true });
          v.src = v.getAttribute("data-src");
        }
        var go = v.play(); if (go && go.catch) go.catch(function () {});
      } else if (!v.paused) v.pause();
    });
  }, { threshold: 0.6 });
  films.forEach(function (v) { io.observe(v); });
});

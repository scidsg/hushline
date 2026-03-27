document.addEventListener("DOMContentLoaded", function () {
  const e = window.HushlineUserSearch,
    t = window.location.pathname.replace(/\/$/, ""),
    n = document.querySelectorAll(".tab[data-tab]"),
    r = document.querySelectorAll(".tab-content"),
    i = document.getElementById("searchInput"),
    a = document.getElementById("clearIcon"),
    o = document.getElementById("directory-search-status"),
    s = document.getElementById("public-record-count"),
    l = document.getElementById("attorney-filters-toggle-shell"),
    c = document.getElementById("attorney-filters-panel-shell"),
    d = document.getElementById("attorney-filters-toggle"),
    u = document.getElementById("attorney-filters-panel"),
    m = document.getElementById("attorney-country-filter"),
    f = document.getElementById("attorney-region-filter"),
    p = new Map();
  let y = [],
    g = !1,
    b = !1,
    h = { countries: [], regions: {} },
    v = null,
    w = null,
    _ = window.location.search;
  function E(e) {
    o && (o.textContent = e);
  }
  function L() {
    if (!d || !u) return;
    const e = !u.hidden;
    d.setAttribute("aria-expanded", e ? "true" : "false"),
      (d.textContent = e ? "Hide Filters" : "Show Filters");
  }
  function k() {
    return (
      document.querySelector(".tab.active")?.getAttribute("data-tab") || "all"
    );
  }
  function A() {
    return (
      document.querySelector(".tab-content.active") ||
      document.getElementById("all")
    );
  }
  function S() {
    return B("", "public-records").length;
  }
  function $() {
    const e = k();
    i &&
      (i.placeholder =
        "verified" !== e
          ? "public-records" !== e
            ? "newsrooms" !== e
              ? "globaleaks" !== e
                ? "securedrop" !== e
                  ? "Search directory..."
                  : "Search SecureDrop instances..."
                : "Search GlobaLeaks instances..."
              : "Search newsrooms..."
            : "Search attorneys..."
          : "Search verified users...");
  }
  function C(e) {
    return "lawyer" === e.account_category;
  }
  function N(e) {
    return "newsroom" === e.account_category;
  }
  function B(t, n = k()) {
    const r = t.trim().toLowerCase();
    return y.filter((t) => {
      if (
        !(function (e, t) {
          if (
            "verified" === t &&
            (!e.is_verified ||
              e.is_public_record ||
              e.is_globaleaks ||
              e.is_newsroom ||
              e.is_securedrop)
          )
            return !1;
          if ("public-records" === t) {
            if (!e.is_public_record && !C(e)) return !1;
            if (
              C(e) &&
              !(function (e) {
                const t = m?.value.trim() || "",
                  n = f?.value.trim() || "";
                return !(
                  (t && e.country !== t) ||
                  (n && e.subdivision_code !== n && e.subdivision !== n)
                );
              })(e)
            )
              return !1;
          }
          return !(
            ("globaleaks" === t && !e.is_globaleaks) ||
            ("newsrooms" === t && !e.is_newsroom && !N(e)) ||
            ("securedrop" === t && !e.is_securedrop)
          );
        })(t, n)
      )
        return !1;
      if ("" === r) return !0;
      const i = Array.isArray(t.countries) ? t.countries.join(" ") : "",
        a = e.normalizeSearchText([
          t.primary_username,
          t.display_name,
          t.bio,
          t.city,
          t.country,
          t.subdivision,
          i,
        ]);
      return e.matchesQuery(a, r);
    });
  }
  function I(e) {
    return e.display_name || e.primary_username || "";
  }
  function H(e, t) {
    return e < t ? -1 : e > t ? 1 : 0;
  }
  function T(e) {
    return (
      e.all_tab_sort_transliterated ?? I(e).normalize("NFKC").toLowerCase()
    );
  }
  function q(e) {
    return e.all_tab_sort_normalized || I(e).normalize("NFKC").toLowerCase();
  }
  function M(e, t) {
    if (e.is_admin !== t.is_admin) return e.is_admin ? -1 : 1;
    if (e.show_caution_badge !== t.show_caution_badge)
      return e.show_caution_badge ? 1 : -1;
    const n = H(T(e), T(t));
    return 0 !== n ? n : H(q(e), q(t));
  }
  function j(t, n) {
    return e.highlightQuery(t || "", n);
  }
  function D(e, t) {
    let n = "";
    return e.is_public_record
      ? ("all" === t &&
          (n +=
            '<span class="badge" role="img" aria-label="Attorney listing">⚖️ Attorney</span>'),
        e.is_automated &&
          (n +=
            '<span class="badge" role="img" aria-label="Automated listing">🤖 Automated</span>'),
        n)
      : e.is_securedrop
        ? ("securedrop" !== t &&
            (n +=
              '<span class="badge" role="img" aria-label="SecureDrop listing">🛡️ SecureDrop</span>'),
          e.is_automated &&
            (n +=
              '<span class="badge" role="img" aria-label="Automated listing">🤖 Automated</span>'),
          n)
        : e.is_newsroom
          ? ("newsrooms" !== t &&
              (n +=
                '<span class="badge" role="img" aria-label="Newsroom listing">📰 Newsroom</span>'),
            e.is_automated &&
              (n +=
                '<span class="badge" role="img" aria-label="Automated listing">🤖 Automated</span>'),
            n)
          : e.is_globaleaks
            ? ("globaleaks" !== t &&
                (n +=
                  '<span class="badge" role="img" aria-label="GlobaLeaks listing">🌐 GlobaLeaks</span>'),
              e.is_automated &&
                (n +=
                  '<span class="badge" role="img" aria-label="Automated listing">🤖 Automated</span>'),
              n)
            : (e.is_admin &&
                (n +=
                  '<span class="badge" role="img" aria-label="Administrator account">⚙️ Admin</span>'),
              e.is_verified &&
                (n +=
                  '<span class="badge" role="img" aria-label="Verified account">⭐️ Verified</span>'),
              e.show_caution_badge &&
                (n +=
                  '<span class="badge badgeCaution" role="img" aria-label="Caution: display name may be mistaken for admin">⚠️ Caution</span>'),
              "all" !== t ||
                e.has_pgp_key ||
                (n +=
                  '<span class="badge" role="img" aria-label="Info-only account">📇 Info Only</span>'),
              n);
  }
  function x(t, n, r, i, a) {
    if (!r.length) return;
    if (n) {
      const e = document.createElement("p");
      (e.className = "label searchLabel"),
        (e.textContent = n),
        t.appendChild(e);
    }
    const o = document.createElement("div");
    (o.className = "user-list"),
      (o.innerHTML = r
        .map((t) =>
          (function (t, n, r) {
            const i = e.escapeHtml(t.display_name || t.primary_username || ""),
              a = e.escapeHtml(t.primary_username || ""),
              o = e.escapeHtml(t.bio || "No bio"),
              s = e.escapeHtml(t.profile_url || "#"),
              l = j(t.display_name || t.primary_username, n),
              c = j(t.primary_username, n),
              d = t.bio ? j(t.bio, n) : "";
            if (
              t.is_public_record ||
              t.is_globaleaks ||
              t.is_newsroom ||
              t.is_securedrop
            )
              return (function (t, n, r) {
                const i = e.escapeHtml(t.display_name || ""),
                  a = e.escapeHtml(t.bio || "No description"),
                  o = e.escapeHtml(t.profile_url || "#"),
                  s = j(t.display_name, n),
                  l = t.bio ? j(t.bio, n) : "";
                let c = "SecureDrop listing";
                return (
                  t.is_public_record
                    ? (c = "Public record listing")
                    : t.is_newsroom
                      ? (c = "Newsroom listing")
                      : t.is_globaleaks && (c = "GlobaLeaks listing"),
                  `\n      <article class="user" aria-label="${e.escapeHtml(c)}, Display name:${i}, Description: ${a}">\n        <h3>${s}</h3>\n        <div class="badgeContainer">${D(t, r)}</div>\n        ${l ? `<p class="bio">${l}</p>` : ""}\n        <div class="user-actions">\n          <a href="${o}" aria-label="View read-only listing for ${i}">View Listing</a>\n        </div>\n      </article>\n    `
                );
              })(t, n, r);
            const u = t.is_admin
                ? (t.is_verified ? "Verified" : "") + " admin user"
                : (t.is_verified ? "Verified" : "") + " User",
              m = e.escapeHtml(u),
              f = D(t, r);
            return `\n      <article class="user" aria-label="${m}, Display name:${i}, Username: ${a}, Bio: ${o}">\n        <h3>${l}</h3>\n        <p class="meta">@${c}</p>\n        ${f ? `<div class="badgeContainer">${f}</div>` : ""}\n        ${d ? `<p class="bio">${d}</p>` : ""}\n        <div class="user-actions">\n          <a href="${s}" aria-label="${i}'s profile">View Profile</a>\n        </div>\n      </article>\n    `;
          })(t, i, a),
        )
        .join("")),
      t.appendChild(o);
  }
  function F(
    e,
    t,
    n,
    r,
    { introMarkup: i = "", showEmptyMessage: a = !0 } = {},
  ) {
    if (((e.innerHTML = i), 0 === t.length))
      return void (
        a &&
        e.insertAdjacentHTML(
          "beforeend",
          '<p class="empty-message"><span class="emoji-message">🫥</span><br>No users found.</p>',
        )
      );
    const o = t.filter(
        (e) =>
          !(
            e.is_public_record ||
            e.is_globaleaks ||
            e.is_newsroom ||
            e.is_securedrop
          ),
      ),
      s = o.filter((e) => e.has_pgp_key),
      l = o.filter((e) => !e.has_pgp_key);
    if ("all" !== r)
      return "verified" === r
        ? (x(e, "", s, n, r), void x(e, "📇 Info-Only Accounts", l, n, r))
        : void x(e, "", t, n, r);
    x(
      e,
      "",
      (function (e) {
        return [...e].sort(M);
      })(t),
      n,
      r,
    );
  }
  function N(e) {
    const t = document.createElement("div"),
      n =
        ((r = e),
        document.getElementById(r)?.querySelector(".dirMeta")?.outerHTML || "");
    var r;
    const i = "public-records" !== e;
    return (
      F(t, B("", e), "", e, { introMarkup: n, showEmptyMessage: i }),
      t.innerHTML
    );
  }
  function U() {
    const e = i.value.trim(),
      t = A(),
      n = (function () {
        const e = k();
        return "verified" === e
          ? "verified users"
          : "public-records" === e
            ? "attorneys"
            : "newsrooms" === e
              ? "newsrooms"
              : "globaleaks" === e
                ? "GlobaLeaks instances"
                : "securedrop" === e
                  ? "SecureDrop instances"
                  : "directory entries";
      })(),
      r = e.length > 0;
    if (
      (a &&
        ((a.style.visibility = r ? "visible" : "hidden"),
        (a.hidden = !r),
        a.setAttribute("aria-hidden", r ? "false" : "true")),
      0 === e.length)
    )
      return (
        t && p.has(t.id) && (t.innerHTML = p.get(t.id)),
        g && E(`Showing all ${n}.`),
        void (g = !1)
      );
    const o = B(e);
    !(function (e, t) {
      const n = A(),
        r = k();
      n && F(n, e, t, r);
    })(o, e),
      E(
        1 === o.length
          ? `Found 1 ${n.slice(0, -1)} matching "${e}".`
          : `Found ${o.length} ${n} matching "${e}".`,
      ),
      (g = !0);
  }
  function O(e) {
    if (!u) return;
    if (
      ((b = e),
      u.setAttribute("aria-busy", e ? "true" : "false"),
      m && (m.disabled = e),
      f)
    ) {
      const t = "true" === f.dataset.disabledByCountry;
      f.disabled = e || t;
    }
    const t = u.querySelector("a");
    t &&
      (t.setAttribute("aria-disabled", e ? "true" : "false"),
      (t.tabIndex = e ? -1 : 0));
  }
  function R() {
    if (!u || !m || !f) return;
    const e = u.querySelector("#attorney-filters-actions");
    e && (e.hidden = !(m.value || f.value));
  }
  function V() {
    if (!m) return;
    const e = m.value,
      t = "true" === m.dataset.showSelectedCount;
    Array.from(m.options).forEach((n) => {
      if (!n.value) return;
      const r = Array.isArray(h.countries)
        ? h.countries.find((e) => e.code === n.value)
        : null;
      r &&
        (n.textContent =
          n.value !== e || t ? `${r.label} (${r.count})` : r.label);
    });
  }
  function P(e, t) {
    e && (e.dataset.showSelectedCount = t ? "true" : "false");
  }
  function z(e, t) {
    e && e.classList.toggle("select-open", t);
  }
  function G(e) {
    P(m, e), P(f, e), V(), Q();
  }
  function K(e) {
    if (!e) return "";
    const t = e.trim().toLowerCase(),
      n = h.regions && "object" == typeof h.regions ? h.regions : {};
    for (const [e, r] of Object.entries(n))
      if (
        Array.isArray(r) &&
        r.find((e) => String(e.code).trim().toLowerCase() === t)
      )
        return e;
    return "";
  }
  function Q() {
    if (!m || !f) return;
    const e = m.value,
      t = f.value,
      n = "true" === f.dataset.showSelectedCount,
      r = h.regions && "object" == typeof h.regions ? h.regions : {},
      i = e
        ? Array.isArray(r[e])
          ? r[e]
          : []
        : Object.values(r).flatMap((e) => (Array.isArray(e) ? e : []));
    (f.innerHTML = '<option value="">All</option>'),
      e
        ? i.forEach((e) => {
            const r = document.createElement("option");
            (r.value = e.code),
              (r.textContent =
                e.code !== t || n ? `${e.label} (${e.count})` : e.label),
              e.code === t && (r.selected = !0),
              f.appendChild(r);
          })
        : Object.entries(r).forEach(([e, r]) => {
            if (!Array.isArray(r) || !r.length) return;
            const i = document.createElement("optgroup");
            (i.label = e),
              r.forEach((e) => {
                const r = document.createElement("option");
                (r.value = e.code),
                  (r.textContent =
                    e.code !== t || n ? `${e.label} (${e.count})` : e.label),
                  e.code === t && (r.selected = !0),
                  i.appendChild(r);
              }),
              f.appendChild(i);
          }),
      i.some((e) => e.code === t) || (f.value = "");
    const a = !i.length;
    (f.dataset.disabledByCountry = a ? "true" : "false"),
      (f.disabled = b || a),
      R();
  }
  function Y() {
    return m && f
      ? v ||
          ((v = fetch(`${t}/attorney-filters.json`)
            .then((e) => {
              if (!e.ok) throw new Error("Network response was not ok");
              return e.json();
            })
            .then((e) => ((h = e), V(), Q(), e))
            .catch(
              (e) => (
                (v = null),
                console.error("Failed to load attorney filter metadata:", e),
                null
              ),
            )),
          v)
      : Promise.resolve(null);
  }
  function J(e) {
    window.history.replaceState(
      {},
      "",
      `${window.location.pathname}${e}${window.location.hash}`,
    );
  }
  function W(e = window.location.search, n = {}) {
    const { showAttorneyFilterLoadingState: r = !1 } = n;
    w && w.abort();
    const i = new AbortController();
    return (
      (w = i),
      r && O(!0),
      (function (e = window.location.search, n = {}) {
        const r = {};
        return (
          n.signal && (r.signal = n.signal),
          fetch(`${t}/users.json${e}`, r)
            .then((e) => {
              if (!e.ok) throw new Error("Network response was not ok");
              return e.json();
            })
            .then((t) => {
              (y = t),
                (_ = e),
                s && (s.textContent = S().toString()),
                document.getElementById("public-records") &&
                  p.set("public-records", N("public-records")),
                document.getElementById("all") && p.set("all", N("all")),
                U();
            })
        );
      })(e, { signal: i.signal }).finally(() => {
        w === i && ((w = null), r && O(!1));
      })
    );
  }
  async function X() {
    if (!u) return;
    const e = (function () {
      const e = new URLSearchParams(window.location.search),
        t = m?.value.trim() || "",
        n = f?.value.trim() || "";
      t ? e.set("country", t) : e.delete("country"),
        n ? e.set("region", n) : e.delete("region");
      const r = e.toString();
      return r ? `?${r}` : "";
    })();
    if (!b && _ !== e) {
      E("Updating attorney results."), J(e);
      try {
        if (
          (await W(e, { showAttorneyFilterLoadingState: !0 }), !i.value.trim())
        ) {
          const e = S();
          E(
            1 === e
              ? "Showing 1 matching attorney."
              : `Showing ${e} matching attorneys.`,
          );
        }
      } catch (e) {
        if ("AbortError" === e.name) return;
        J(_),
          (function (e) {
            if (!m || !f) return;
            const t = new URLSearchParams(e);
            (m.value = t.get("country") || ""),
              (f.value = t.get("region") || ""),
              !m.value && f.value && (m.value = K(f.value)),
              V(),
              Q(),
              u && ((u.hidden = !(m.value || f.value)), L(), R());
          })(_),
          E("Unable to update attorney results."),
          console.error("Failed to update attorney results:", e);
      }
    }
  }
  if (
    (r.forEach((e) => {
      p.set(e.id, e.innerHTML);
    }),
    i && i.addEventListener("input", U),
    a &&
      a.addEventListener("click", function () {
        i &&
          ((i.value = ""),
          (a.style.visibility = "hidden"),
          (a.hidden = !0),
          a.setAttribute("aria-hidden", "true"),
          U());
      }),
    d &&
      u &&
      (L(),
      d.addEventListener("click", function () {
        (u.hidden = !u.hidden), L();
      })),
    u && m && f)
  ) {
    const e = u.querySelector("a"),
      t = function (e) {
        ("keydown" === e.type &&
          "ArrowDown" !== e.key &&
          "ArrowUp" !== e.key &&
          "Enter" !== e.key &&
          " " !== e.key) ||
          G(!0);
      },
      n = function () {
        G(!1);
      },
      r = function (e) {
        ("keydown" === e.type &&
          "ArrowDown" !== e.key &&
          "ArrowUp" !== e.key &&
          "Enter" !== e.key &&
          " " !== e.key) ||
          z(e.currentTarget, !0);
      },
      i = function (e) {
        z(e.currentTarget, !1);
      };
    m.addEventListener("change", async function () {
      await Y(), V(), Q(), n(), z(m, !1), X();
    }),
      f.addEventListener("change", function () {
        !m.value && f.value && ((m.value = K(f.value)), Q()),
          V(),
          R(),
          n(),
          z(f, !1),
          X();
      }),
      m.addEventListener("focus", t),
      m.addEventListener("pointerdown", t),
      m.addEventListener("keydown", t),
      m.addEventListener("blur", n),
      m.addEventListener("pointerdown", r),
      m.addEventListener("keydown", r),
      m.addEventListener("blur", i),
      f.addEventListener("focus", t),
      f.addEventListener("pointerdown", t),
      f.addEventListener("keydown", t),
      f.addEventListener("blur", n),
      f.addEventListener("pointerdown", r),
      f.addEventListener("keydown", r),
      f.addEventListener("blur", i),
      e &&
        e.addEventListener("click", function (e) {
          e.preventDefault(),
            b || ((m.value = ""), (f.value = ""), V(), Q(), n(), X());
        });
  }
  (window.activateTab = function (e) {
    const t = document.getElementById(e.getAttribute("aria-controls"));
    t &&
      (r.forEach((e) => {
        (e.hidden = !0),
          (e.style.display = "none"),
          e.classList.remove("active");
      }),
      n.forEach((e) => {
        e.setAttribute("aria-selected", "false"), e.classList.remove("active");
      }),
      e.setAttribute("aria-selected", "true"),
      e.classList.add("active"),
      (t.hidden = !1),
      (t.style.display = "block"),
      t.classList.add("active"),
      (function () {
        const e = "public-records" === k();
        l && (l.hidden = !e), c && (c.hidden = !e);
      })(),
      $(),
      U());
  }),
    n.forEach((e) => {
      e.addEventListener("click", function (e) {
        const t = e.currentTarget,
          n = document.querySelector(".directory-sticky-shell"),
          r = document.querySelector(".directory-tabs");
        if (
          t.classList.contains("active") &&
          ((n && n.classList.contains("is-sticky")) ||
            (r && r.classList.contains("is-sticky")))
        ) {
          const e = window.matchMedia(
            "(prefers-reduced-motion: reduce)",
          ).matches;
          return void window.scrollTo({
            top: 0,
            behavior: e ? "auto" : "smooth",
          });
        }
        window.activateTab(t);
      }),
        e.addEventListener("keydown", function (e) {
          if ("ArrowLeft" !== e.key && "ArrowRight" !== e.key) return;
          e.preventDefault();
          const t = Array.from(n),
            r = t.indexOf(e.currentTarget),
            i =
              t[(r + ("ArrowRight" === e.key ? 1 : -1) + t.length) % t.length];
          i && (window.activateTab(i), i.focus());
        });
    });
  const Z = document.querySelector(".tab.active") || n[0];
  Z && window.activateTab(Z);
  const ee = document.querySelector(".directory-sticky-shell"),
    te = document.querySelector(".directory-tabs"),
    ne = document.querySelector(".directory-search");
  if (te || ee) {
    const e = () => {
      const e = document.querySelector("header"),
        t = document.querySelector(".banner"),
        n =
          (e ? e.getBoundingClientRect().height : 0) +
          (t ? t.getBoundingClientRect().height : 0),
        r = ee || te;
      if (r) {
        r.style.setProperty("--directory-sticky-top", `${n}px`);
        const e = r.getBoundingClientRect().top,
          t = window.scrollY > n + 1 && e <= n;
        ee?.classList.toggle("is-sticky", t),
          te?.classList.toggle("is-sticky", t),
          ne?.classList.toggle("is-sticky", t);
      }
    };
    e(),
      window.addEventListener("scroll", e, { passive: !0 }),
      window.addEventListener("hashchange", () => {
        requestAnimationFrame(e);
      }),
      window.addEventListener("resize", e);
  }
  $(),
    Y(),
    W().catch((e) => {
      "AbortError" !== e.name && console.error("Failed to load user data:", e);
    });
});

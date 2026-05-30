document.addEventListener("DOMContentLoaded", function () {
  const e = {
      au: "Australia",
      at: "Austria",
      be: "Belgium",
      fi: "Finland",
      fr: "France",
      de: "Germany",
      in: "India",
      it: "Italy",
      jp: "Japan",
      lu: "Luxembourg",
      nl: "Netherlands",
      pt: "Portugal",
      sg: "Singapore",
      es: "Spain",
      se: "Sweden",
      us: "United States",
    },
    t = window.HushlineUserSearch,
    n = window.location.pathname.replace(/\/$/, ""),
    r = document.getElementById("directory-tabs"),
    a = document.getElementById("directory-tab-list"),
    i = r?.querySelector(".scroll-left"),
    o = r?.querySelector(".scroll-right"),
    l = window.matchMedia("(min-width: 641px)"),
    s = document.querySelectorAll(".tab[data-tab]"),
    c = document.querySelectorAll(".tab-content"),
    u = document.getElementById("searchInput"),
    d = document.getElementById("clearIcon"),
    g = document.getElementById("directory-search-status"),
    m = document.getElementById("public-record-count"),
    p = document.getElementById("newsroom-count"),
    y = document.getElementById("all-filters-toggle-shell"),
    f = document.getElementById("all-filters-panel-shell"),
    b = document.getElementById("all-filters-toggle"),
    h = document.getElementById("all-filters-panel"),
    w = document.getElementById("all-country-filter"),
    v = document.getElementById("all-region-filter"),
    L = document.getElementById("all-listing-type-filter"),
    S = document.getElementById("attorney-filters-toggle-shell"),
    F = document.getElementById("attorney-filters-panel-shell"),
    E = document.getElementById("attorney-filters-toggle"),
    _ = document.getElementById("attorney-filters-panel"),
    C = document.getElementById("attorney-country-filter"),
    $ = document.getElementById("attorney-region-filter"),
    A = document.getElementById("newsroom-filters-toggle-shell"),
    k = document.getElementById("newsroom-filters-panel-shell"),
    T = document.getElementById("newsroom-filters-toggle"),
    B = document.getElementById("newsroom-filters-panel"),
    I = document.getElementById("newsroom-country-filter"),
    P = document.getElementById("newsroom-region-filter"),
    M = new Map(),
    x = new Map(),
    R = new Map(),
    q = new Map();
  let N = !1,
    j = null,
    H = null,
    O = window.location.search;
  function V(e) {
    g && (g.textContent = e);
  }
  function U(t) {
    const n = t?.trim() || "";
    return n ? e[n.toLowerCase()] || n : "";
  }
  function D() {
    return (
      document.querySelector(".tab.active")?.getAttribute("data-tab") || "all"
    );
  }
  function z() {
    return (
      document.querySelector(".tab-content.active") ||
      document.getElementById("all")
    );
  }
  function G() {
    if (!(r && a && i && o)) return;
    const e = a.scrollWidth - a.clientWidth,
      t = l.matches && e > 1,
      n = t && a.scrollLeft > 1,
      s = t && a.scrollLeft < e - 1;
    r.classList.toggle("directory-tabs-overflowing", t),
      (i.hidden = !n),
      (o.hidden = !s);
  }
  function W(e) {
    if (!a) return;
    const t = window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      n = Math.max(0.75 * a.clientWidth, 200),
      r = Math.max(a.scrollWidth - a.clientWidth, 0),
      i = Math.min(Math.max(a.scrollLeft + e * n, 0), r);
    a.scrollTo({ left: i, behavior: t ? "auto" : "smooth" });
  }
  function K() {
    const e = D();
    u &&
      (u.placeholder =
        "verified" !== e
          ? "public-records" !== e
            ? "newsrooms" !== e
              ? "globaleaks" !== e
                ? "securedrop" !== e
                  ? "Search directory..."
                  : "Search SecureDrop instances..."
                : "Search GlobaLeaks instances..."
              : "Search journalists and newsrooms..."
            : "Search attorneys..."
          : "Search verified users...");
  }
  function Q() {
    const e = D();
    return "verified" === e
      ? "verified users"
      : "public-records" === e
        ? "attorneys"
        : "newsrooms" === e
          ? "journalists and newsrooms"
          : "globaleaks" === e
            ? "GlobaLeaks instances"
            : "securedrop" === e
              ? "SecureDrop instances"
              : "directory entries";
  }
  function J(e) {
    return "lawyer" === e.account_category;
  }
  function Y(e, n = D()) {
    const r = e.trim().toLowerCase();
    return (function (e = D()) {
      return x.get(e) || [];
    })(n).filter((e) => {
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
            if (!e.is_public_record && !J(e)) return !1;
            if (
              J(e) &&
              !(function (e) {
                const t = C?.value.trim() || "",
                  n = $?.value.trim() || "";
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
            ("newsrooms" === t &&
              !e.is_newsroom &&
              !(function (e) {
                return (
                  "journalist" === e.account_category ||
                  "newsroom" === e.account_category ||
                  "journalist_newsroom" === e.account_category
                );
              })(e)) ||
            ("securedrop" === t && !e.is_securedrop)
          );
        })(e, n)
      )
        return !1;
      if ("" === r) return !0;
      const a = Array.isArray(e.countries) ? e.countries.join(" ") : "",
        i = t.normalizeSearchText([
          e.primary_username,
          e.display_name,
          e.bio,
          e.city,
          e.country,
          e.subdivision,
          a,
        ]);
      return t.matchesQuery(i, r);
    });
  }
  function X(e) {
    return e.display_name || e.primary_username || "";
  }
  function Z(e, t) {
    return e < t ? -1 : e > t ? 1 : 0;
  }
  function ee(e) {
    return (
      e.all_tab_sort_transliterated ?? X(e).normalize("NFKC").toLowerCase()
    );
  }
  function te(e) {
    return e.all_tab_sort_normalized || X(e).normalize("NFKC").toLowerCase();
  }
  function ne(e, t) {
    if (e.is_admin !== t.is_admin) return e.is_admin ? -1 : 1;
    if (e.show_caution_badge !== t.show_caution_badge)
      return e.show_caution_badge ? 1 : -1;
    const n = Z(ee(e), ee(t));
    return 0 !== n ? n : Z(te(e), te(t));
  }
  function re(e, n) {
    return t.highlightQuery(e || "", n);
  }
  function ae(e, t) {
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
              ("all" !== t && "public-records" !== t && "newsrooms" !== t) ||
                e.has_pgp_key ||
                (n +=
                  '<span class="badge" role="img" aria-label="Info-only account">📇 Info Only</span>'),
              n);
  }
  function ie(e, n, r, a, i) {
    if (!r.length) return;
    if (n) {
      const t = document.createElement("p");
      (t.className = "label searchLabel"),
        (t.textContent = n),
        e.appendChild(t);
    }
    const o = document.createElement("div");
    (o.className = "user-list"),
      (o.innerHTML = r
        .map((e) =>
          (function (e, n, r) {
            const a = t.escapeHtml(e.display_name || e.primary_username || ""),
              i = t.escapeHtml(e.primary_username || ""),
              o = t.escapeHtml(e.bio || "No bio"),
              l = t.escapeHtml(e.profile_url || "#"),
              s = re(e.display_name || e.primary_username, n),
              c = re(e.primary_username, n),
              u = e.bio ? re(e.bio, n) : "";
            if (
              e.is_public_record ||
              e.is_globaleaks ||
              e.is_newsroom ||
              e.is_securedrop
            )
              return (function (e, n, r) {
                const a = t.escapeHtml(e.display_name || ""),
                  i = t.escapeHtml(e.bio || "No description"),
                  o = t.escapeHtml(e.profile_url || "#"),
                  l = re(e.display_name, n),
                  s = e.bio ? re(e.bio, n) : "";
                let c = "SecureDrop listing";
                return (
                  e.is_public_record
                    ? (c = "Public record listing")
                    : e.is_newsroom
                      ? (c = "Newsroom listing")
                      : e.is_globaleaks && (c = "GlobaLeaks listing"),
                  `\n      <article class="user" aria-label="${t.escapeHtml(c)}, Display name:${a}, Description: ${i}">\n        <h3>${l}</h3>\n        <div class="badgeContainer">${ae(e, r)}</div>\n        ${s ? `<p class="bio">${s}</p>` : ""}\n        <div class="user-actions">\n          <a href="${o}" aria-label="View read-only listing for ${a}">View Listing</a>\n        </div>\n      </article>\n    `
                );
              })(e, n, r);
            const d = e.is_admin
                ? (e.is_verified ? "Verified" : "") + " admin user"
                : (e.is_verified ? "Verified" : "") + " User",
              g = t.escapeHtml(d),
              m = ae(e, r);
            return `\n      <article class="user" aria-label="${g}, Display name:${a}, Username: ${i}, Bio: ${o}">\n        <h3>${s}</h3>\n        <p class="meta">@${c}</p>\n        ${m ? `<div class="badgeContainer">${m}</div>` : ""}\n        ${u ? `<p class="bio">${u}</p>` : ""}\n        <div class="user-actions">\n          <a href="${l}" aria-label="${a}'s profile">View Profile</a>\n        </div>\n      </article>\n    `;
          })(e, a, i),
        )
        .join("")),
      e.appendChild(o);
  }
  function oe(
    e,
    t,
    n,
    r,
    { introMarkup: a = "", showEmptyMessage: i = !0 } = {},
  ) {
    if (((e.innerHTML = a), 0 === t.length))
      return void (
        i &&
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
      l = o.filter((e) => e.has_pgp_key),
      s = o.filter((e) => !e.has_pgp_key);
    if ("all" !== r)
      return "verified" === r
        ? (ie(e, "", l, n, r), void ie(e, "📇 Info-Only Accounts", s, n, r))
        : void ie(e, "", t, n, r);
    ie(
      e,
      "",
      (function (e) {
        return [...e].sort(ne);
      })(t),
      n,
      r,
    );
  }
  function le(e) {
    return (
      document.getElementById(e)?.querySelector(".dirMeta")?.outerHTML || ""
    );
  }
  function se(e = ["public-records", "newsrooms", "all"]) {
    e.forEach((e) => {
      document.getElementById(e) &&
        M.set(
          e,
          (function (e) {
            const t = document.createElement("div"),
              n = le(e),
              r = "public-records" !== e;
            return (
              oe(t, Y("", e), "", e, { introMarkup: n, showEmptyMessage: r }),
              t.innerHTML
            );
          })(e),
        );
    });
  }
  function ce() {
    const e = u.value.trim(),
      t = z(),
      n = D(),
      r = Q(),
      a = e.length > 0;
    if (
      (d &&
        ((d.style.visibility = a ? "visible" : "hidden"),
        (d.hidden = !a),
        d.setAttribute("aria-hidden", a ? "false" : "true")),
      0 === e.length)
    )
      return (
        t && M.has(t.id) && (t.innerHTML = M.get(t.id)),
        N && V(`Showing all ${r}.`),
        void (N = !1)
      );
    if (!x.has(n))
      return (
        V(`Loading ${r}.`),
        void ge(n)
          .then(() => {
            ce();
          })
          .catch((e) => {
            "AbortError" !== e.name &&
              (V(`Unable to load ${r}.`),
              console.error(`Failed to load ${r}:`, e));
          })
      );
    const i = Y(e);
    !(function (e, t) {
      const n = z(),
        r = D();
      n && oe(n, e, t, r);
    })(i, e),
      V(
        1 === i.length
          ? `Found 1 ${r.slice(0, -1)} matching "${e}".`
          : `Found ${i.length} ${r} matching "${e}".`,
      ),
      (N = !0);
  }
  function ue(e, t) {
    const n = new URLSearchParams(e);
    t.forEach((e) => {
      n.delete(e);
    });
    const r = n.toString();
    return r ? `?${r}` : "";
  }
  function de(e, t) {
    return "all" === e
      ? (function (e) {
          return ue(e, [
            "country",
            "region",
            "newsroom_country",
            "newsroom_region",
          ]);
        })(t)
      : (function (e) {
          return ue(e, ["all_country", "all_region", "all_listing_type"]);
        })(t);
  }
  function ge(e, t = window.location.search, r = {}) {
    const a = de(e, t),
      i = `${e}\n${a}`;
    if (R.get(e) === a && x.has(e)) return Promise.resolve(x.get(e));
    if (q.has(i)) return q.get(i);
    const o = {};
    r.signal && (o.signal = r.signal);
    const l = fetch(
      `${n}/users.json${(function (e, t) {
        const n = new URLSearchParams(de(e, t));
        n.set("tab", e);
        const r = n.toString();
        return r ? `?${r}` : `?tab=${encodeURIComponent(e)}`;
      })(e, t)}`,
      o,
    )
      .then((e) => {
        if (!e.ok) throw new Error("Network response was not ok");
        return e.json();
      })
      .then((t) => (x.set(e, t), R.set(e, a), se([e]), t))
      .finally(() => {
        q.delete(i);
      });
    return q.set(i, l), l;
  }
  function me(e) {
    const t = {
      ...e,
      loading: !1,
      metadata: { countries: [], regions: {} },
      metadataRequest: null,
    };
    return t.countryFilter && t.regionFilter
      ? ((t.hasActiveFilters = function () {
          return Boolean(
            t.countryFilter.value.trim() ||
              t.regionFilter.value.trim() ||
              t.listingTypeFilter?.value.trim(),
          );
        }),
        (t.activeFilterCount = function () {
          return [
            t.countryFilter.value.trim(),
            t.regionFilter.value.trim(),
            t.listingTypeFilter?.value.trim() || "",
          ].filter(Boolean).length;
        }),
        (t.updateToggle = function () {
          if (!t.toggle || !t.panel) return;
          const e = !t.panel.hidden,
            n = t.activeFilterCount(),
            r = t.toggle.querySelector("[data-filter-toggle-label]"),
            a = t.toggle.querySelector("[data-filter-toggle-badge]"),
            i = e ? "Hide Filters" : "Show Filters";
          t.toggle.setAttribute("aria-expanded", e ? "true" : "false"),
            r ? (r.textContent = i) : (t.toggle.textContent = i),
            a &&
              ((a.hidden = e || 0 === n),
              (a.textContent = n.toString()),
              a.setAttribute("aria-label", `${n} active filters`));
        }),
        (t.updateVisibility = function () {
          const e = D() === t.tabName;
          t.toggleShell && (t.toggleShell.hidden = !e),
            t.panelShell && (t.panelShell.hidden = !e);
        }),
        (t.resultsCount = function () {
          return Y("", t.tabName).length;
        }),
        (t.updateCountBadge = function () {
          t.countBadge &&
            (t.countBadge.textContent = t.resultsCount().toString());
        }),
        (t.buildSearch = function () {
          const e = new URLSearchParams(window.location.search),
            n = t.countryFilter.value.trim(),
            r = t.regionFilter.value.trim();
          if (
            (n ? e.set(t.countryParam, n) : e.delete(t.countryParam),
            r ? e.set(t.regionParam, r) : e.delete(t.regionParam),
            t.listingTypeParam)
          ) {
            const n = t.listingTypeFilter?.value.trim() || "";
            n ? e.set(t.listingTypeParam, n) : e.delete(t.listingTypeParam);
          }
          const a = e.toString();
          return a ? `?${a}` : "";
        }),
        (t.setSelectExpandedState = function (e, t) {
          e && (e.dataset.showSelectedCount = t ? "true" : "false");
        }),
        (t.setSelectOpenState = function (e, t) {
          e && e.classList.toggle("select-open", t);
        }),
        (t.updateClearVisibility = function () {
          if (!t.panel) return;
          const e = t.panel.querySelector(`#${t.actionsId}`);
          e && (e.hidden = !t.hasActiveFilters());
        }),
        (t.countryLabelForValue = function (e) {
          if (!e) return "";
          const n = Array.isArray(t.metadata.countries)
            ? t.metadata.countries.find((t) => t.code === e)
            : null;
          if (n?.label) return n.label;
          const r = Array.from(t.countryFilter.options).find(
            (t) => t.value === e,
          );
          return r?.textContent
            ? r.textContent.replace(/\s+\(\d+\)$/, "")
            : U(e);
        }),
        (t.updateCountryLabels = function () {
          const e = t.countryFilter.value,
            n = "true" === t.countryFilter.dataset.showSelectedCount,
            r = Array.isArray(t.metadata.countries)
              ? [...t.metadata.countries]
              : [];
          e &&
            !r.some((t) => t.code === e) &&
            r.unshift({ code: e, label: t.countryLabelForValue(e), count: 0 }),
            (t.countryFilter.innerHTML = '<option value="">All</option>'),
            r.forEach((r) => {
              const a = document.createElement("option");
              (a.value = r.code),
                (a.textContent =
                  r.code !== e || n ? `${r.label} (${r.count})` : r.label),
                r.code === e && (a.selected = !0),
                t.countryFilter.appendChild(a);
            }),
            r.some((t) => t.code === e) || (t.countryFilter.value = "");
        }),
        (t.updateListingTypeLabels = function () {
          if (!t.listingTypeFilter) return;
          const e = t.listingTypeFilter.value,
            n = "true" === t.listingTypeFilter.dataset.showSelectedCount,
            r = Array.isArray(t.metadata.listing_types)
              ? [...t.metadata.listing_types]
              : [],
            a = Array.from(t.listingTypeFilter.options).find(
              (t) => t.value === e,
            );
          e &&
            !r.some((t) => t.code === e) &&
            r.unshift({
              code: e,
              label: a?.textContent?.replace(/\s+\(\d+\)$/, "") || e,
              count: 0,
            }),
            (t.listingTypeFilter.innerHTML = '<option value="">All</option>'),
            r.forEach((r) => {
              const a = document.createElement("option");
              (a.value = r.code),
                (a.textContent =
                  r.code !== e || n ? `${r.label} (${r.count})` : r.label),
                r.code === e && (a.selected = !0),
                t.listingTypeFilter.appendChild(a);
            }),
            r.some((t) => t.code === e) || (t.listingTypeFilter.value = "");
        }),
        (t.inferredCountryForRegionCode = function (e) {
          if (!e) return "";
          const n = e.trim().toLowerCase(),
            r =
              t.metadata.regions && "object" == typeof t.metadata.regions
                ? t.metadata.regions
                : {};
          for (const [e, t] of Object.entries(r))
            if (
              Array.isArray(t) &&
              t.find((e) => String(e.code).trim().toLowerCase() === n)
            )
              return e;
          return "";
        }),
        (t.updateRegionOptions = function () {
          const e = t.countryFilter.value,
            n = t.regionFilter.value,
            r = "true" === t.regionFilter.dataset.showSelectedCount,
            a =
              t.metadata.regions && "object" == typeof t.metadata.regions
                ? t.metadata.regions
                : {},
            i = e
              ? Array.isArray(a[e])
                ? a[e]
                : []
              : Object.values(a).flatMap((e) => (Array.isArray(e) ? e : []));
          (t.regionFilter.innerHTML = '<option value="">All</option>'),
            e
              ? i.forEach((e) => {
                  const a = document.createElement("option");
                  (a.value = e.code),
                    (a.textContent =
                      e.code !== n || r ? `${e.label} (${e.count})` : e.label),
                    e.code === n && (a.selected = !0),
                    t.regionFilter.appendChild(a);
                })
              : Object.entries(a).forEach(([e, a]) => {
                  if (!Array.isArray(a) || !a.length) return;
                  const i = document.createElement("optgroup");
                  (i.label = e),
                    a.forEach((e) => {
                      const t = document.createElement("option");
                      (t.value = e.code),
                        (t.textContent =
                          e.code !== n || r
                            ? `${e.label} (${e.count})`
                            : e.label),
                        e.code === n && (t.selected = !0),
                        i.appendChild(t);
                    }),
                    t.regionFilter.appendChild(i);
                }),
            i.some((e) => e.code === n) || (t.regionFilter.value = "");
          const o = !i.length;
          (t.regionFilter.dataset.disabledByCountry = o ? "true" : "false"),
            (t.regionFilter.disabled = t.loading || o),
            t.updateClearVisibility();
        }),
        (t.updateSelectExpandedLabels = function (e) {
          t.setSelectExpandedState(t.countryFilter, e),
            t.setSelectExpandedState(t.regionFilter, e),
            t.setSelectExpandedState(t.listingTypeFilter, e),
            t.updateCountryLabels(),
            t.updateRegionOptions(),
            t.updateListingTypeLabels();
        }),
        (t.applyFromSearch = function (e) {
          const n = new URLSearchParams(e);
          (t.countryFilter.value = U(n.get(t.countryParam))),
            (t.regionFilter.value = n.get(t.regionParam) || ""),
            t.listingTypeFilter &&
              t.listingTypeParam &&
              (t.listingTypeFilter.value = n.get(t.listingTypeParam) || ""),
            !t.countryFilter.value &&
              t.regionFilter.value &&
              (t.countryFilter.value = t.inferredCountryForRegionCode(
                t.regionFilter.value,
              )),
            t.updateCountryLabels(),
            t.updateRegionOptions(),
            t.updateListingTypeLabels(),
            t.panel && (t.updateToggle(), t.updateClearVisibility());
        }),
        (t.setLoadingState = function (e) {
          if (!t.panel) return;
          (t.loading = e),
            t.panel.setAttribute("aria-busy", e ? "true" : "false"),
            (t.countryFilter.disabled = e);
          const n = "true" === t.regionFilter.dataset.disabledByCountry;
          (t.regionFilter.disabled = e || n),
            t.listingTypeFilter && (t.listingTypeFilter.disabled = e);
          const r = t.panel.querySelector("a");
          r &&
            (r.setAttribute("aria-disabled", e ? "true" : "false"),
            (r.tabIndex = e ? -1 : 0));
        }),
        (t.ensureMetadata = function (e = window.location.search) {
          if (t.metadataRequest && t.metadataSearch === e)
            return t.metadataRequest;
          let r;
          (t.metadataSearch = e), (r = fetch(`${n}/${t.metadataPath}${e}`));
          const a = r
            .then((e) => {
              if (!e.ok) throw new Error("Network response was not ok");
              return e.json();
            })
            .then(
              (n) => (
                t.metadataSearch !== e ||
                  ((t.metadata = n), t.applyFromSearch(e)),
                n
              ),
            )
            .catch(
              (n) => (
                t.metadataSearch === e && (t.metadataRequest = null),
                console.error(
                  `Failed to load ${t.resultsLabelPlural} filter metadata:`,
                  n,
                ),
                null
              ),
            );
          return (t.metadataRequest = a), a;
        }),
        (t.refreshResults = async function () {
          if (!t.panel) return;
          const e = t.buildSearch(),
            n = de(t.tabName, e);
          if (!(t.loading || (R.get(t.tabName) === n && x.has(t.tabName)))) {
            V(`Updating ${t.resultsLabelPlural} results.`), ye(e);
            try {
              if ((await fe(e, { loadingController: t }), !u.value.trim())) {
                const e = t.resultsCount();
                V(
                  1 === e
                    ? `Showing 1 matching ${t.resultsLabelSingular}.`
                    : `Showing ${e} matching ${t.resultsLabelPlural}.`,
                );
              }
            } catch (e) {
              if ("AbortError" === e.name) return;
              ye(O),
                t.applyFromSearch(O),
                V(`Unable to update ${t.resultsLabelPlural} results.`),
                console.error(
                  `Failed to update ${t.resultsLabelPlural} results:`,
                  e,
                );
            }
          }
        }),
        (t.bindEvents = function () {
          if (
            (t.toggle &&
              t.panel &&
              (t.updateToggle(),
              t.toggle.addEventListener("click", function () {
                (t.panel.hidden = !t.panel.hidden), t.updateToggle();
              })),
            !t.panel)
          )
            return;
          const e = t.panel.querySelector("a"),
            n = function (e) {
              ("keydown" === e.type &&
                "ArrowDown" !== e.key &&
                "ArrowUp" !== e.key &&
                "Enter" !== e.key &&
                " " !== e.key) ||
                t.updateSelectExpandedLabels(!0);
            },
            r = function () {
              t.updateSelectExpandedLabels(!1);
            },
            a = function (e) {
              ("keydown" === e.type &&
                "ArrowDown" !== e.key &&
                "ArrowUp" !== e.key &&
                "Enter" !== e.key &&
                " " !== e.key) ||
                t.setSelectOpenState(e.currentTarget, !0);
            },
            i = function (e) {
              t.setSelectOpenState(e.currentTarget, !1);
            };
          t.countryFilter.addEventListener("change", function () {
            t.updateCountryLabels(),
              t.updateRegionOptions(),
              r(),
              t.setSelectOpenState(t.countryFilter, !1),
              t.refreshResults();
          }),
            t.regionFilter.addEventListener("change", function () {
              !t.countryFilter.value &&
                t.regionFilter.value &&
                ((t.countryFilter.value = t.inferredCountryForRegionCode(
                  t.regionFilter.value,
                )),
                t.updateRegionOptions()),
                t.updateCountryLabels(),
                t.updateClearVisibility(),
                r(),
                t.setSelectOpenState(t.regionFilter, !1),
                t.refreshResults();
            }),
            t.listingTypeFilter &&
              t.listingTypeFilter.addEventListener("change", function () {
                t.updateListingTypeLabels(),
                  t.updateClearVisibility(),
                  r(),
                  t.setSelectOpenState(t.listingTypeFilter, !1),
                  t.refreshResults();
              }),
            [t.countryFilter, t.regionFilter, t.listingTypeFilter]
              .filter(Boolean)
              .forEach((e) => {
                e.addEventListener("focus", n),
                  e.addEventListener("pointerdown", n),
                  e.addEventListener("keydown", n),
                  e.addEventListener("blur", r),
                  e.addEventListener("pointerdown", a),
                  e.addEventListener("keydown", a),
                  e.addEventListener("blur", i);
              }),
            e &&
              e.addEventListener("click", function (e) {
                e.preventDefault(),
                  t.loading ||
                    ((t.countryFilter.value = ""),
                    (t.regionFilter.value = ""),
                    t.listingTypeFilter && (t.listingTypeFilter.value = ""),
                    t.updateCountryLabels(),
                    t.updateRegionOptions(),
                    t.updateListingTypeLabels(),
                    r(),
                    t.refreshResults());
              });
        }),
        t)
      : null;
  }
  c.forEach((e) => {
    M.set(e.id, e.innerHTML);
  });
  const pe = [
    me({
      tabName: "all",
      toggleShell: y,
      panelShell: f,
      toggle: b,
      panel: h,
      countryFilter: w,
      regionFilter: v,
      listingTypeFilter: L,
      actionsId: "all-filters-actions",
      metadataPath: "all-filters.json",
      countryParam: "all_country",
      regionParam: "all_region",
      listingTypeParam: "all_listing_type",
      resultsLabelSingular: "directory entry",
      resultsLabelPlural: "directory entries",
    }),
    me({
      tabName: "public-records",
      countBadge: m,
      toggleShell: S,
      panelShell: F,
      toggle: E,
      panel: _,
      countryFilter: C,
      regionFilter: $,
      actionsId: "attorney-filters-actions",
      metadataPath: "attorney-filters.json",
      countryParam: "country",
      regionParam: "region",
      resultsLabelSingular: "attorney",
      resultsLabelPlural: "attorneys",
    }),
    me({
      tabName: "newsrooms",
      countBadge: p,
      toggleShell: A,
      panelShell: k,
      toggle: T,
      panel: B,
      countryFilter: I,
      regionFilter: P,
      actionsId: "newsroom-filters-actions",
      metadataPath: "newsroom-filters.json",
      countryParam: "newsroom_country",
      regionParam: "newsroom_region",
      resultsLabelSingular: "journalist or newsroom",
      resultsLabelPlural: "journalists and newsrooms",
    }),
  ].filter(Boolean);
  function ye(e) {
    window.history.replaceState(
      {},
      "",
      `${window.location.pathname}${e}${window.location.hash}`,
    );
  }
  function fe(e = window.location.search, t = {}) {
    const { loadingController: n = null } = t,
      r = n?.tabName || D();
    j && j.abort(), H && H !== n && H.setLoadingState(!1);
    const a = new AbortController();
    (j = a),
      (H = n),
      n && n.setLoadingState(!0),
      x.has(r) ||
        (function (e) {
          const t = document.getElementById(e);
          if (!t) return;
          const n = le(e);
          t.innerHTML = `${n}<p class="empty-message" role="status">Loading...</p>`;
        })(r);
    const i =
        n ||
        (function (e) {
          return pe.find((t) => t.tabName === e) || null;
        })(r),
      o = i ? i.ensureMetadata(e) : Promise.resolve(null);
    return Promise.all([ge(r, e, { signal: a.signal }), o])
      .then(() => {
        (O = e),
          pe.forEach((e) => {
            x.has(e.tabName) && e.updateCountBadge();
          }),
          se([r]),
          ce();
      })
      .finally(() => {
        j === a &&
          ((j = null), H === n && (n && n.setLoadingState(!1), (H = null)));
      });
  }
  u && u.addEventListener("input", ce),
    d &&
      d.addEventListener("click", function () {
        u &&
          ((u.value = ""),
          (d.style.visibility = "hidden"),
          (d.hidden = !0),
          d.setAttribute("aria-hidden", "true"),
          ce());
      }),
    pe.forEach((e) => {
      e.bindEvents();
    }),
    (window.activateTab = function (e) {
      const t = document.getElementById(e.getAttribute("aria-controls"));
      t &&
        (c.forEach((e) => {
          (e.hidden = !0),
            (e.style.display = "none"),
            e.classList.remove("active");
        }),
        s.forEach((e) => {
          e.setAttribute("aria-selected", "false"),
            e.classList.remove("active");
        }),
        e.setAttribute("aria-selected", "true"),
        e.classList.add("active"),
        (t.hidden = !1),
        (t.style.display = "block"),
        t.classList.add("active"),
        e.scrollIntoView({ block: "nearest", inline: "nearest" }),
        pe.forEach((e) => {
          e.updateVisibility();
        }),
        K(),
        ce(),
        "verified" !== e.getAttribute("data-tab") &&
          fe().catch((e) => {
            "AbortError" !== e.name &&
              (V(`Unable to load ${Q()}.`),
              console.error("Failed to load directory tab data:", e));
          }),
        requestAnimationFrame(G));
    }),
    s.forEach((e) => {
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
          const t = Array.from(s),
            n = t.indexOf(e.currentTarget),
            r =
              t[(n + ("ArrowRight" === e.key ? 1 : -1) + t.length) % t.length];
          r && (window.activateTab(r), r.focus());
        });
    });
  const be = document.querySelector(".tab.active") || s[0];
  be && window.activateTab(be);
  const he = document.querySelector(".directory-sticky-shell"),
    we = document.querySelector(".directory-search");
  if (r || he) {
    const e = () => {
      const e = document.querySelector("header"),
        t = document.querySelector(".banner"),
        n =
          (e ? e.getBoundingClientRect().height : 0) +
          (t ? t.getBoundingClientRect().height : 0),
        a = he || r;
      if (a) {
        a.style.setProperty("--directory-sticky-top", `${n}px`);
        const e = a.getBoundingClientRect().top,
          t = window.scrollY > n + 1 && e <= n;
        he?.classList.toggle("is-sticky", t),
          r?.classList.toggle("is-sticky", t),
          we?.classList.toggle("is-sticky", t);
      }
    };
    e(),
      window.addEventListener("scroll", e, { passive: !0 }),
      window.addEventListener("hashchange", () => {
        requestAnimationFrame(e);
      }),
      window.addEventListener("resize", e);
  }
  a &&
    i &&
    o &&
    (i.addEventListener("click", function () {
      W(-1);
    }),
    o.addEventListener("click", function () {
      W(1);
    }),
    a.addEventListener("scroll", G, { passive: !0 }),
    window.addEventListener("resize", G),
    "function" == typeof l.addEventListener
      ? l.addEventListener("change", G)
      : "function" == typeof l.addListener && l.addListener(G),
    G()),
    K();
});

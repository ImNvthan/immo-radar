/* Interactivité de la page de suivi : critères, classement en direct et analyseur d'annonce.
   Tout reste dans le navigateur (localStorage). Rien n'est envoyé nulle part. */
(function () {
  'use strict';
  var node = document.getElementById('donnees');
  if (!node) return;
  var D = JSON.parse(node.textContent);
  var C = D.communes, T = D.types;
  var root = document.documentElement, body = document.body;
  root.classList.add('js');

  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function esc(x) { return String(x).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function norm(s) { return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[-'’_.,]/g, ' ').replace(/\s+/g, ' ').trim(); }
  function nombre(x, d) { return Number(x).toLocaleString('fr-FR', { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }); }
  function pct(x, signe) { return (signe && x > 0 ? '+' : '') + nombre(x * 100, 1) + ' %'; }
  function num(x, def) { x = parseFloat(String(x).replace(',', '.')); return isFinite(x) && x >= 0 ? x : def; }

  var store = {
    get: function (k, d) { try { var v = localStorage.getItem('radar.' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set: function (k, v) { try { localStorage.setItem('radar.' + k, JSON.stringify(v)); } catch (e) { /* stockage indisponible */ } }
  };

  /* ---- réglages (valeurs de départ du radar, modifiables ici) ---- */
  var R0 = { min: D.min_ventes, coef: D.loyer_coef, dApp: D.loyer_defaut.Appartement, dMai: D.loyer_defaut.Maison,
    marge: D.seuils.marge_negociation, decote: D.seuils.decote_min, rend: D.seuils.rendement_net_min, charges: D.seuils.charges_et_vacance };
  var R = Object.assign({}, R0, store.get('reglages', {}));
  var ov = store.get('loyers', {});
  function majLoyers() {
    C.forEach(function (c) {
      var o = ov[c.k + '|' + c.t];
      if (o > 0) { c.lv = o; c.lo = 'saisi par toi'; }
      else if (c.b !== null && c.b !== undefined) { c.lv = c.b * R.coef; c.lo = c.o; }
      else if (c.o === 'config.yml') { c.lv = c.l; c.lo = c.o; }
      else { c.lv = c.t === 'Maison' ? R.dMai : R.dApp; c.lo = 'défaut des réglages'; }
      c.rr = c.lv * 12 / c.p;
    });
  }
  var CH = { 'r-min': ['min', 1], 'r-coef': ['coef', 100], 'r-lapp': ['dApp', 1], 'r-lmai': ['dMai', 1],
    'r-marge': ['marge', 100], 'r-decote': ['decote', 100], 'r-rend': ['rend', 100], 'r-charges': ['charges', 100] };
  function afficherReglages() {
    Object.keys(CH).forEach(function (id) { $('#' + id).value = Math.round(R[CH[id][0]] * CH[id][1] * 1000) / 1000; });
  }
  function toutRecalculer() { majLoyers(); rendreCommunes(); rendreAnnonces(); resultatLive(); }
  Object.keys(CH).forEach(function (id) {
    $('#' + id).addEventListener('input', function () {
      var v = parseFloat(this.value);
      if (!isFinite(v) || v < 0) return;
      R[CH[id][0]] = v / CH[id][1]; store.set('reglages', R); toutRecalculer();
    });
  });
  $('#r-reset').addEventListener('click', function () {
    Object.assign(R, R0); ov = {}; store.set('reglages', {}); store.set('loyers', {}); afficherReglages(); toutRecalculer();
  });
  $('#r-dep').addEventListener('change', function () {
    location.href = (this.dataset.prefixe || '') + 'd/' + this.value + '/index.html';
  });

  var saved = store.get('criteres', {});
  var etat = {
    type: T[0],
    budget: num(saved.budget, D.budget_max),
    surface: num(saved.surface, D.surface_min),
    q: '', tri: saved.tri || 'rendement', fav: !!saved.fav
  };
  var favoris = store.get('favoris', []);
  var annonces = store.get('annonces', []);

  function sauverCriteres() { store.set('criteres', { budget: etat.budget, surface: etat.surface, tri: etat.tri, fav: etat.fav }); }

  /* ---- commutateur de type de bien ---- */
  var boutons = $$('.commutateur button');
  function choisirType(t) {
    etat.type = t;
    body.setAttribute('data-type', t);
    boutons.forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.type === t); });
    var sel = $('#a-type'); if (sel) { sel.value = t; majListeCommunes(); }
    rendreCommunes(); rendreAnnonces(); resultatLive();
  }
  boutons.forEach(function (b) { b.addEventListener('click', function () { choisirType(b.dataset.type); }); });
  if (boutons.length) $('.commutateur').hidden = false;

  /* ---- critères ---- */
  var fBudget = $('#c-budget'), fSurface = $('#c-surface'), fQ = $('#c-q'), fTri = $('#c-tri'), fFav = $('#c-fav');
  fBudget.value = etat.budget || ''; fSurface.value = etat.surface || ''; fTri.value = etat.tri; fFav.checked = etat.fav;
  function lireCriteres() {
    etat.budget = num(fBudget.value, 0); etat.surface = num(fSurface.value, 0);
    etat.q = fQ.value; etat.tri = fTri.value; etat.fav = fFav.checked;
    sauverCriteres(); rendreCommunes(); rendreAnnonces(); resultatLive();
  }
  [fBudget, fSurface, fQ, fTri, fFav].forEach(function (f) { f.addEventListener('input', lireCriteres); f.addEventListener('change', lireCriteres); });
  $('#c-reset').addEventListener('click', function () {
    fBudget.value = ''; fSurface.value = ''; fQ.value = ''; fTri.value = 'rendement'; fFav.checked = false; lireCriteres();
  });

  /* ---- classement des communes ---- */
  var TRIS = {
    rendement: function (a, b) { return b.rr - a.rr; },
    prix: function (a, b) { return a.p - b.p; },
    evolution: function (a, b) { return (a.e === null) - (b.e === null) || a.e - b.e; },
    ventes: function (a, b) { return b.n - a.n; }
  };
  function selection() {
    var q = norm(etat.q);
    return C.filter(function (c) {
      if (c.t !== etat.type || c.n < R.min) return false;
      if (etat.budget > 0 && etat.surface > 0 && c.p * etat.surface > etat.budget) return false;
      if (q && norm(c.c).indexOf(q) < 0) return false;
      if (etat.fav && favoris.indexOf(c.k) < 0) return false;
      return true;
    }).sort(TRIS[etat.tri] || TRIS.rendement);
  }
  function classeEvo(e) { return e === null ? '' : e > 0.02 ? 'hausse' : e < -0.02 ? 'baisse' : ''; }
  function rendreCommunes() {
    var cible = $('#liste-communes'); if (!cible) return;
    var l = selection(), max = 0.0001;
    l.forEach(function (c) { if (c.rr > max) max = c.rr; });
    var html = l.slice(0, 30).map(function (c) {
      var est = favoris.indexOf(c.k) >= 0;
      var achat = etat.budget > 0 ? '<span class="tag">pour ' + nombre(etat.budget) + ' € : environ ' + nombre(etat.budget / c.p) + ' m²</span>' : '';
      return '<li class="commune"><span class="nom">' + esc(c.c) +
        '<button type="button" class="etoile" data-k="' + esc(c.k) + '" aria-pressed="' + est + '" aria-label="' + (est ? 'Retirer ' : 'Suivre ') + esc(c.c) + '">' + (est ? '★' : '☆') + '</button></span>' +
        '<span class="rend">' + nombre(c.rr * 100, 1) + ' %</span>' +
        '<span class="barre"><i style="width:' + Math.round(c.rr / max * 100) + '%"></i></span>' +
        '<span class="det"><span>' + nombre(c.p) + ' €/m²</span><span>' + c.n + ' ventes</span>' +
        '<span class="tag ' + classeEvo(c.e) + '">' + (c.e === null ? 'n/d' : pct(c.e, true)) + ' sur 12 mois</span>' +
        '<span>loyer ' + nombre(c.lv, 1) + '\u00a0€/m² (' + esc(c.lo) + ')</span>' + achat + '</span><label class="ovl">Ajuster le loyer (€/m²) <input class="ov" type="number" step="any" min="0" data-k="' + esc(c.k) + '" data-t="' + esc(c.t) + '" value="' + (ov[c.k + '|' + c.t] || '') + '" placeholder="' + nombre(c.lv, 1) + '"></label></li>';
    }).join('');
    var plus = l.length > 30 ? ' Les 30 premières sont affichées.' : '';
    $('#compte-communes').textContent = l.length + ' commune' + (l.length > 1 ? 's' : '') + ' correspond' + (l.length > 1 ? 'ent' : '') + '.' + plus;
    cible.innerHTML = l.length ? '<ol class="communes">' + html + '</ol>' :
      '<div class="vide"><b>Aucune commune ne correspond.</b>Élargis le budget, baisse la surface minimale ou efface la recherche.</div>';
  }
  $('#liste-communes').addEventListener('change', function (ev) {
    var f = ev.target.closest('.ov'); if (!f) return;
    var cle = f.dataset.k + '|' + f.dataset.t, v = parseFloat(f.value);
    if (isFinite(v) && v > 0) ov[cle] = v; else delete ov[cle];
    store.set('loyers', ov); toutRecalculer();
  });
  $('#liste-communes').addEventListener('click', function (ev) {
    var b = ev.target.closest('.etoile'); if (!b) return;
    var k = b.dataset.k, i = favoris.indexOf(k);
    if (i >= 0) favoris.splice(i, 1); else favoris.push(k);
    store.set('favoris', favoris); rendreCommunes();
  });

  /* ---- analyseur d'annonce ---- */
  var aType = $('#a-type'), aCommune = $('#a-commune'), aSurface = $('#a-surface'), aPrix = $('#a-prix'), aLoyer = $('#a-loyer'), aUrl = $('#a-url');
  function majListeCommunes() {
    $('#liste-noms').innerHTML = C.filter(function (c) { return c.t === aType.value; })
      .sort(function (a, b) { return b.n - a.n; }).map(function (c) { return '<option value="' + esc(c.c) + '">'; }).join('');
  }
  function trouver(nom, type) {
    var n = norm(nom), best = null;
    C.forEach(function (c) { if (c.t === type && norm(c.c) === n && (!best || c.n > best.n)) best = c; });
    return best;
  }
  function evaluer(a) {
    var c = trouver(a.commune, a.type);
    if (!c) return { err: 'Commune inconnue pour ce type de bien. Choisis-en une dans la liste proposée.' };
    if (!(a.surface > 0 && a.prix > 0)) return { err: 'Renseigne le prix et la surface de l’annonce.' };
    var pm2 = a.prix * (1 - R.marge) / a.surface;
    var ecart = pm2 / c.p - 1;
    var loyer = a.loyer > 0 ? a.loyer : c.lv, orig = a.loyer > 0 ? 'saisi par toi' : c.lo;
    var net = loyer * a.surface * 12 * (1 - R.charges) / a.prix;
    var hors = '';
    if (etat.budget > 0 && a.prix > etat.budget) hors = 'Hors de ton budget';
    else if (etat.surface > 0 && a.surface < etat.surface) hors = 'Sous ta surface minimale';
    var okPrix = ecart <= -R.decote, okRend = net >= R.rend;
    var opp = !hors && okPrix && okRend;
    var txt = hors ? hors + '.' :
      opp ? 'Opportunité : la décote et le rendement dépassent tes seuils.' :
      okPrix ? 'Bon prix, mais le rendement net reste sous le seuil de ' + pct(R.rend) + '.' :
      okRend ? 'Rendement correct, mais le prix est proche du marché.' :
      'Prix au niveau du marché ou au-dessus, rendement sous le seuil.';
    return { c: c, pm2: pm2, ecart: ecart, loyer: loyer, orig: orig, net: net, hors: hors, opp: opp, txt: txt };
  }
  function lireAnnonce() {
    return { type: aType.value, commune: aCommune.value, surface: num(aSurface.value, 0), prix: num(aPrix.value, 0), loyer: num(aLoyer.value, 0), url: aUrl.value.trim() };
  }
  function carteResultat(r, a) {
    if (r.err) return '<div class="vide">' + esc(r.err) + '</div>';
    var faible = r.c.n >= R.min ? '' : '<p class="legende">Échantillon faible dans cette commune (' + r.c.n + ' ventes) : résultat peu fiable.</p>';
    return '<div class="verdict ' + (r.opp ? 'oui' : r.hors ? 'non' : '') + '"><b>' + esc(r.txt) + '</b></div>' +
      '<dl class="chiffres"><div><dt>Prix au m² (après négociation)</dt><dd>' + nombre(r.pm2) + ' €</dd></div>' +
      '<div><dt>Médiane des ventes de ' + esc(r.c.c) + '</dt><dd>' + nombre(r.c.p) + ' €/m²</dd></div>' +
      '<div><dt>Écart au marché</dt><dd class="' + (r.ecart < 0 ? 'baisse' : 'hausse') + '">' + pct(r.ecart, true) + '</dd></div>' +
      '<div><dt>Rendement net estimé</dt><dd>' + pct(r.net) + '</dd></div>' +
      '<div><dt>Loyer retenu</dt><dd>' + nombre(r.loyer, 1) + ' €/m²<small>' + esc(r.orig) + '</small></dd></div></dl>' + faible;
  }
  function resultatLive() {
    var a = lireAnnonce(), z = $('#resultat');
    if (!a.commune && !aPrix.value && !aSurface.value) { z.innerHTML = ''; $('#a-enreg').disabled = true; return; }
    var r = evaluer(a); z.innerHTML = carteResultat(r, a); $('#a-enreg').disabled = !!r.err;
  }
  [aType, aCommune, aSurface, aPrix, aLoyer].forEach(function (f) { f.addEventListener('input', resultatLive); f.addEventListener('change', resultatLive); });
  aType.addEventListener('change', function () { majListeCommunes(); choisirType(aType.value); });
  $('#form-annonce').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var a = lireAnnonce(); if (evaluer(a).err) return;
    if (a.url && !/^https?:\/\//i.test(a.url)) a.url = '';
    a.id = Date.now(); annonces.push(a); store.set('annonces', annonces);
    aSurface.value = aPrix.value = aLoyer.value = aUrl.value = ''; resultatLive(); rendreAnnonces();
  });
  function rendreAnnonces() {
    var cible = $('#mes-annonces'); if (!cible) return;
    var lignes = annonces.map(function (a) { return { a: a, r: evaluer(a) }; }).filter(function (x) { return !x.r.err; })
      .sort(function (x, y) { return x.r.ecart - y.r.ecart; });
    $('#nb-annonces').textContent = lignes.length ? '(' + lignes.length + ')' : '';
    if (!lignes.length) { cible.innerHTML = '<div class="vide"><b>Aucune annonce enregistrée.</b>Analyse une annonce ci-dessus puis enregistre-la : elle reste sur cet appareil et se compare automatiquement à tes critères.</div>'; return; }
    cible.innerHTML = '<div class="opps">' + lignes.map(function (x) {
      var a = x.a, r = x.r;
      var lien = a.url ? '<a class="voir" href="' + esc(a.url) + '" rel="noopener noreferrer" target="_blank">Voir l’annonce</a>' : '';
      return '<article class="opp ' + (r.opp ? 'top' : '') + '"><span class="decote ' + (r.ecart < 0 ? '' : 'cher') + '">' + pct(r.ecart, true) + '</span>' +
        '<span class="mono">' + (r.opp ? 'opportunité' : 'vs médiane DVF') + '</span><span class="lieu">' + esc(r.c.c) + '</span>' +
        '<span>' + esc(a.type) + ' · ' + nombre(a.surface) + ' m² · ' + nombre(a.prix) + ' €</span><span>Rendement net ' + pct(r.net) + '</span>' +
        '<span class="legende">' + esc(r.txt) + '</span>' + lien +
        '<button type="button" class="suppr" data-id="' + a.id + '">Supprimer</button></article>';
    }).join('') + '</div>';
  }
  $('#mes-annonces').addEventListener('click', function (ev) {
    var b = ev.target.closest('.suppr'); if (!b) return;
    annonces = annonces.filter(function (a) { return String(a.id) !== b.dataset.id; });
    store.set('annonces', annonces); rendreAnnonces();
  });

  /* ---- import de texte collé (annonces ou e-mail d'alerte) ---- */
  var noms = [];
  (function () {
    var vus = {};
    C.forEach(function (c) { var n = norm(c.c); if (!vus[n]) { vus[n] = 1; noms.push(n); } });
    noms.sort(function (a, b) { return b.length - a.length; });
  })();
  /* Un lien d'annonce ne contient jamais le prix, mais souvent le type de bien et la commune. */
  function depuisUrl(url) {
    var chemin;
    try { chemin = decodeURIComponent(new URL(url).pathname); } catch (e) { return {}; }
    var slug = ' ' + norm(chemin.replace(/[\/_]/g, ' ')) + ' ', res = {};
    if (/ (appartement|appart|studio|duplex|loft|t[1-6]|f[1-6]) /.test(slug)) res.type = 'Appartement';
    else if (/ (maison|pavillon|villa|longere|fermette) /.test(slug)) res.type = 'Maison';
    for (var i = 0; i < noms.length; i++) { if (slug.indexOf(' ' + noms[i] + ' ') >= 0) { res.commune = noms[i]; break; } }
    var m = chemin.toLowerCase().match(/(\d{2,3})\s?m(?:2|²)/);
    if (m) res.surface = parseFloat(m[1]);
    return res;
  }
  aUrl.addEventListener('input', function () {
    var u = aUrl.value.trim(), h = $('#url-aide');
    if (!/^https?:\/\/\S+$/i.test(u)) { h.textContent = ''; return; }
    var d = depuisUrl(u), trouve = [];
    if (d.type && aType.value !== d.type) { choisirType(d.type); }
    if (d.type) trouve.push(d.type.toLowerCase());
    if (d.commune && !aCommune.value) { var c = trouverNorm(d.commune, aType.value) || trouverNorm(d.commune, null); if (c) { aCommune.value = c.c; trouve.push(c.c); } }
    if (d.surface && !aSurface.value) { aSurface.value = d.surface; trouve.push(d.surface + ' m²'); }
    h.textContent = trouve.length ? 'Lu dans le lien : ' + trouve.join(', ') + '. Il reste à saisir le prix' + (aSurface.value ? '' : ' et la surface') + '.' :
      'Ce lien ne contient ni commune ni type de bien. Saisis les informations de l’annonce ou colle son texte plus bas.';
    resultatLive();
  });
  var RE_URL =/https?:\/\/[^\s<>"')]+/gi;
  function lireNombre(s) { return parseFloat(String(s).replace(/[\s  .]/g, '').replace(',', '.')); }
  function analyserBloc(txt, urlBloc) {
    var t = txt.replace(/\s+/g, ' ');
    var prix = null, m, rp = /(^|[^\w.,])(\d{1,3}(?:[\s  .]\d{3})+|\d{4,8})\s*(?:€|euros?\b)/gi;
    while ((m = rp.exec(t))) { var v = lireNombre(m[2]); if (v >= 10000 && v <= 10000000) { prix = v; break; } }
    var surface = null, rs = /(\d{1,4}(?:[.,]\d{1,2})?)\s*m(?:²|2)/gi;
    while ((m = rs.exec(t))) { var s = parseFloat(m[1].replace(',', '.')); if (s >= 9 && s <= 1000) { surface = s; break; } }
    var n = ' ' + norm(t) + ' ', commune = null;
    for (var i = 0; i < noms.length; i++) { if (n.indexOf(' ' + noms[i] + ' ') >= 0) { commune = noms[i]; break; } }
    var type = /\b(appartement|appart|studio|duplex|loft)\b|\b[tf][1-6]\b/i.test(t) ? 'Appartement' :
      /\b(maison|pavillon|villa|longere|longère|fermette)\b/i.test(t) ? 'Maison' : etat.type;
    var nom = null, uu = urlBloc || ((t.match(/https?:\/\/[^\s<>"')]+/i) || [''])[0]);
    if (uu) { var du = depuisUrl(uu); if (!commune && du.commune) commune = du.commune; if (!surface && du.surface) surface = du.surface; if (du.type && !/\b(appartement|maison)/i.test(t)) type = du.type; }
    if (commune) { var c = trouverNorm(commune, type) || trouverNorm(commune, null); nom = c ? c.c : null; }
    var u = urlBloc || ((t.match(/https?:\/\/[^\s<>"')]+/i) || [''])[0]);
    return { type: type, commune: nom || '', surface: surface || 0, prix: prix || 0, loyer: 0, url: /^https?:\/\//i.test(u) ? u : '', ok: !!(nom && surface && prix) };
  }
  function trouverNorm(n, type) {
    var best = null;
    C.forEach(function (c) { if ((type === null || c.t === type) && norm(c.c) === n && (!best || c.n > best.n)) best = c; });
    return best;
  }
  function decouper(texte) {
    var urls = texte.match(RE_URL) || [];
    var blocs = texte.split(/\n\s*\n/).filter(function (b) { return b.trim(); });
    if (blocs.length <= 1 && urls.length > 1) {
      blocs = []; var reste = texte, deb = 0, mm; RE_URL.lastIndex = 0;
      while ((mm = RE_URL.exec(texte))) { blocs.push(texte.slice(deb, mm.index + mm[0].length)); deb = mm.index + mm[0].length; }
    }
    return blocs;
  }
  var colles = [];
  $('#p-analyser').addEventListener('click', function () {
    var blocs = decouper($('#p-texte').value), ignores = 0;
    colles = [];
    blocs.forEach(function (b) { var a = analyserBloc(b); if (a.ok) colles.push(a); else if (/[€\d]/.test(b)) ignores++; });
    colles = colles.map(function (a) { return { a: a, r: evaluer(a) }; }).filter(function (x) { return !x.r.err; })
      .sort(function (x, y) { return x.r.ecart - y.r.ecart; });
    var z = $('#p-resultats');
    if (!colles.length) { z.innerHTML = '<div class="vide"><b>Aucune annonce reconnue.</b>Colle le texte tel qu’il apparaît : il faut au moins un prix en €, une surface en m² et le nom d’une commune de la zone.</div>'; return; }
    z.innerHTML = '<p class="legende">' + colles.length + ' annonce' + (colles.length > 1 ? 's' : '') + ' reconnue' + (colles.length > 1 ? 's' : '') +
      (ignores ? ', ' + ignores + ' ignorée' + (ignores > 1 ? 's' : '') + ' (prix, surface ou commune introuvable)' : '') + ', classées de la plus forte décote à la plus faible.</p>' +
      '<div class="opps">' + colles.map(function (x, i) {
        var a = x.a, r = x.r;
        return '<article class="opp ' + (r.opp ? 'top' : '') + '"><span class="decote ' + (r.ecart < 0 ? '' : 'cher') + '">' + pct(r.ecart, true) + '</span>' +
          '<span class="mono">' + (r.opp ? 'opportunité' : 'vs médiane DVF') + '</span><span class="lieu">' + esc(r.c.c) + '</span>' +
          '<span>' + esc(a.type) + ' · ' + nombre(a.surface) + ' m² · ' + nombre(a.prix) + ' €</span><span>Rendement net ' + pct(r.net) + '</span>' +
          '<span class="legende">' + esc(r.txt) + '</span><button type="button" class="btn sec garder" data-i="' + i + '">Enregistrer</button></article>';
      }).join('') + '</div><div class="actions"><button type="button" class="btn" id="p-tout">Tout enregistrer</button></div>';
  });
  function garder(liste) {
    liste.forEach(function (x, k) { var a = Object.assign({}, x.a); delete a.ok; a.id = Date.now() + k; annonces.push(a); });
    store.set('annonces', annonces); rendreAnnonces();
  }
  $('#p-resultats').addEventListener('click', function (ev) {
    var b = ev.target.closest('button'); if (!b) return;
    if (b.id === 'p-tout') { garder(colles); colles = []; $('#p-resultats').innerHTML = '<div class="vide"><b>Annonces enregistrées.</b>Retrouve-les dans « Mes annonces enregistrées ».</div>'; $('#p-texte').value = ''; }
    else if (b.classList.contains('garder')) { garder([colles[+b.dataset.i]]); b.textContent = 'Enregistrée'; b.disabled = true; }
  });

  majLoyers(); afficherReglages();
  aType.innerHTML = T.map(function (t) { return '<option value="' + esc(t) + '">' + esc(t) + '</option>'; }).join('');
  choisirType(T[0]);
})();

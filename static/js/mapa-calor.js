/* ReConecta — mapa de calor do /dashboard.
   Contornos dos 27 estados: malha oficial do IBGE (static/geo/brasil.topo.json, ver static/geo/FONTES.md),
   desenhados aqui em SVG; o calor é pintado em Canvas e recortado pelo contorno do Brasil.
   Sem tiles externos, sem chave e sem biblioteca: o TopoJSON é decodificado abaixo.

   Cor de cada ponto do país = média entre (a) as refeições potenciais da UF (suavizadas na divisa)
   e (b) a concentração em torno dos municípios de quem recebeu: kernel gaussiano em que cada sede
   vale, no centro, as suas próprias refeições. As duas parcelas estão em refeições potenciais.
   Escala linear: Baixo = 0, Médio = metade, Alto = a maior UF (acima disso fica no vermelho). */
(function () {
  "use strict";
  var SVG = "http://www.w3.org/2000/svg";
  // recorte do mapa (graus) e projeção equirretangular corrigida pela latitude média
  var OESTE = -74.6, LESTE = -32.4, NORTE = 5.9, SUL = -34.2, PX = 20;
  var KX = Math.cos(15 * Math.PI / 180);
  var LARGURA = Math.round((LESTE - OESTE) * KX * PX), ALTURA = Math.round((NORTE - SUL) * PX);
  var SIGMA_GRAUS = 2;     // desvio do kernel (~220 km)
  var DIVISA_GRAUS = 0.6;  // suavização da cor da UF na divisa (~65 km)
  var PASSO = 2;           // px de tela por célula da grade do calor
  // paleta da referência: azul → verde → amarelo → laranja → vermelho
  var PALETA = [[0, "#22409A"], [0.15, "#2C6FD0"], [0.3, "#35AFC4"], [0.42, "#7CCB5A"],
                [0.5, "#F2E234"], [0.68, "#F6A02C"], [0.85, "#E5432A"], [1, "#A50F1F"]];
  // rótulos das UFs pequenas ficam no mar, com linha de chamada (lon, lat)
  var ROTULO_FORA = { RN: [-33.6, -5.0], PB: [-33.4, -6.9], PE: [-33.6, -8.6], AL: [-34.2, -10.2],
                      SE: [-35.3, -11.9], ES: [-37.9, -20.3], RJ: [-40.4, -24.4], DF: [-45.6, -14.4] };

  function projetar(p) { return [(p[0] - OESTE) * KX * PX, (NORTE - p[1]) * PX]; }

  var cores = (function () {
    var tabela = [];
    function rgb(h) { return [1, 3, 5].map(function (i) { return parseInt(h.substr(i, 2), 16); }); }
    for (var i = 0; i < 256; i++) {
      var t = i / 255, j = 1;
      while (j < PALETA.length - 1 && PALETA[j][0] < t) j++;
      var a = PALETA[j - 1], b = PALETA[j], f = (t - a[0]) / (b[0] - a[0]);
      var ca = rgb(a[1]), cb = rgb(b[1]);
      tabela.push([0, 1, 2].map(function (k) { return Math.round(ca[k] + (cb[k] - ca[k]) * f); }));
    }
    return tabela;
  })();

  /* ---------- TopoJSON (só o necessário: arcos quantizados, Polygon e MultiPolygon) ---------- */
  function decodificar(topo) {
    var s = topo.transform.scale, tr = topo.transform.translate;
    var arcos = topo.arcs.map(function (arco) {
      var x = 0, y = 0;
      return arco.map(function (p) { x += p[0]; y += p[1]; return projetar([x * s[0] + tr[0], y * s[1] + tr[1]]); });
    });
    function anel(indices) {
      var pontos = [];
      indices.forEach(function (i) {
        var a = i < 0 ? arcos[~i].slice().reverse() : arcos[i];
        pontos.push.apply(pontos, pontos.length ? a.slice(1) : a);
      });
      return pontos;
    }
    function caminho(g) {
      var poligonos = g.type === "Polygon" ? [g.arcs] : g.type === "MultiPolygon" ? g.arcs : [];
      return poligonos.map(function (aneis) {
        return aneis.map(function (indices) {
          return "M" + anel(indices).map(function (p) { return p[0].toFixed(1) + " " + p[1].toFixed(1); }).join("L") + "Z";
        }).join("");
      }).join("");
    }
    return {
      ufs: topo.objects.ufs.geometries.map(function (g) {
        return { uf: g.properties.uf, nome: g.properties.nome, d: caminho(g), rotulo: projetar([g.properties.rx, g.properties.ry]) };
      }),
      vizinhos: topo.objects.vizinhos.geometries.map(caminho)
    };
  }

  var malha = null;
  function carregarMalha() {
    if (!malha) {
      malha = fetch("/static/geo/brasil.topo.json", { credentials: "same-origin" })
        .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
        .then(decodificar)
        .catch(function (erro) { malha = null; throw erro; });
    }
    return malha;
  }

  function no(tag, attrs, texto) {
    var n = document.createElementNS(SVG, tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (texto != null) n.textContent = texto;
    return n;
  }

  /* desfoque de caixa separável, 2 passadas (aproxima um gaussiano) */
  function suavizar(v, w, h, r) {
    var tmp = new Float32Array(v.length), x, y, s, n = 2 * r + 1;
    for (var passada = 0; passada < 2; passada++) {
      for (y = 0; y < h; y++) {
        s = 0;
        for (x = -r; x <= r; x++) s += v[y * w + Math.min(w - 1, Math.max(0, x))];
        for (x = 0; x < w; x++) {
          tmp[y * w + x] = s / n;
          s += v[y * w + Math.min(w - 1, x + r + 1)] - v[y * w + Math.max(0, x - r)];
        }
      }
      for (x = 0; x < w; x++) {
        s = 0;
        for (y = -r; y <= r; y++) s += tmp[Math.min(h - 1, Math.max(0, y)) * w + x];
        for (y = 0; y < h; y++) {
          v[y * w + x] = s / n;
          s += tmp[Math.min(h - 1, y + r + 1) * w + x] - tmp[Math.max(0, y - r) * w + x];
        }
      }
    }
  }

  /* ---------- campo de calor ---------- */
  function pintarCalor(canvas, geo, dados, larguraCss) {
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var alturaCss = larguraCss * ALTURA / LARGURA;
    canvas.width = Math.round(larguraCss * dpr);
    canvas.height = Math.round(alturaCss * dpr);
    var gw = Math.ceil(larguraCss / PASSO), gh = Math.ceil(alturaCss / PASSO);
    var escala = gw / LARGURA;

    // (a) valor da UF: cada estado pintado com sua fração do máximo, lido de volta
    var grade = document.createElement("canvas");
    grade.width = gw; grade.height = gh;
    var g = grade.getContext("2d", { willReadFrequently: true });
    g.setTransform(escala, 0, 0, escala, 0, 0);
    geo.ufs.forEach(function (u) {
      var v = Math.round(255 * (dados.porUf[u.uf] || 0) / dados.maximo);
      g.fillStyle = "rgb(" + v + "," + v + "," + v + ")";
      g.fill(new Path2D(u.d), "evenodd");
    });
    var lida = g.getImageData(0, 0, gw, gh).data, base = new Float32Array(gw * gh);
    for (var b = 0; b < base.length; b++) base[b] = lida[b * 4] / 255 * dados.maximo;
    suavizar(base, gw, gh, Math.max(1, Math.round(DIVISA_GRAUS * PX * escala)));

    // (b) kernel gaussiano a partir da sede de cada município, peso = refeições potenciais
    var calor = new Float32Array(gw * gh);
    var sigma = SIGMA_GRAUS * PX * escala, raio = Math.ceil(3 * sigma), dois = 2 * sigma * sigma;
    dados.pontos.forEach(function (p) {
      if (!(p.peso > 0)) return;
      var c = projetar([p.lon, p.lat]), cx = c[0] * escala, cy = c[1] * escala;
      for (var y = Math.max(0, Math.floor(cy - raio)); y <= Math.min(gh - 1, Math.ceil(cy + raio)); y++) {
        for (var x = Math.max(0, Math.floor(cx - raio)); x <= Math.min(gw - 1, Math.ceil(cx + raio)); x++) {
          var dx = x + 0.5 - cx, dy = y + 0.5 - cy;
          calor[y * gw + x] += p.peso * Math.exp(-(dx * dx + dy * dy) / dois);
        }
      }
    });

    var imagem = g.createImageData(gw, gh), px = imagem.data;
    for (var k = 0; k < gw * gh; k++) {
      var t = (0.5 * base[k] + 0.5 * calor[k]) / dados.maximo;
      var c = cores[Math.min(255, Math.round(t * 255))];
      px[k * 4] = c[0]; px[k * 4 + 1] = c[1]; px[k * 4 + 2] = c[2]; px[k * 4 + 3] = 255;
    }
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.putImageData(imagem, 0, 0);

    var ctx = canvas.getContext("2d");
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    var s = canvas.width / LARGURA;
    ctx.setTransform(s, 0, 0, s, 0, 0);
    ctx.save();
    var brasil = new Path2D();
    geo.ufs.forEach(function (u) { brasil.addPath(new Path2D(u.d)); });
    ctx.clip(brasil, "nonzero");
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(grade, 0, 0, gw, gh, 0, 0, gw / escala, gh / escala);
    ctx.restore();
  }

  /* ---------- mapa ---------- */
  var formato = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
  var formatoKg = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

  function montar(alvo, geo, entrada) {
    var porUf = {}, linhas = {};
    (entrada.porUf || []).forEach(function (r) { porUf[r.uf] = r.refeicoes_estimadas || 0; linhas[r.uf] = r; });
    var maximo = Math.max.apply(null, Object.keys(porUf).map(function (k) { return porUf[k]; }).concat([1]));
    var dados = { porUf: porUf, maximo: maximo,
                  pontos: (entrada.porMunicipio || []).map(function (m) { return { lat: m.lat, lon: m.lon, peso: m.refeicoes_estimadas }; }) };

    var moldura = document.createElement("div");
    moldura.className = "mapa-calor__moldura";
    var canvas = document.createElement("canvas");
    canvas.className = "mapa-calor__calor";
    canvas.setAttribute("aria-hidden", "true");
    var svg = no("svg", { viewBox: "0 0 " + LARGURA + " " + ALTURA, class: "mapa-calor__svg", "aria-hidden": "true", focusable: "false" });
    var fundo = no("g", { class: "mapa-calor__fundo" });
    geo.vizinhos.forEach(function (d) { fundo.appendChild(no("path", { d: d })); });
    fundo.appendChild(no("text", { x: projetar([-36, -26])[0], y: projetar([-36, -26])[1], class: "mapa-calor__oceano" }, "OCEANO"));
    fundo.appendChild(no("text", { x: projetar([-36, -27.3])[0], y: projetar([-36, -27.3])[1], class: "mapa-calor__oceano" }, "ATLÂNTICO"));
    var estados = no("g", { class: "mapa-calor__ufs" });
    var rotulos = no("g", { class: "mapa-calor__rotulos" });
    geo.ufs.forEach(function (u) {
      var caminho = no("path", { d: u.d, "data-uf": u.uf, "fill-rule": "evenodd" });
      estados.appendChild(caminho);
      var fora = ROTULO_FORA[u.uf], pos = fora ? projetar(fora) : u.rotulo;
      if (fora) rotulos.appendChild(no("line", { x1: u.rotulo[0], y1: u.rotulo[1], x2: pos[0], y2: pos[1], class: "mapa-calor__chamada" }));
      rotulos.appendChild(no("text", { x: pos[0], y: pos[1], "data-uf": u.uf }, u.uf));
    });
    svg.append(fundo, estados, rotulos);

    var dica = document.createElement("div");
    dica.className = "mapa-calor__dica";
    dica.setAttribute("aria-hidden", "true");
    dica.hidden = true;
    moldura.append(canvas, svg, dica);

    var legenda = document.createElement("div");
    legenda.className = "mapa-calor__legenda";
    [["mapa-calor__barra", []], ["mapa-calor__marcas", ["Baixo", "Médio", "Alto"]],
     ["mapa-calor__valores", ["0", formato.format(maximo / 2), formato.format(maximo) + " refeições potenciais"]]].forEach(function (l) {
      var linha = document.createElement("span");
      linha.className = l[0];
      l[1].forEach(function (t) { var s = document.createElement("span"); s.textContent = t; linha.appendChild(s); });
      legenda.appendChild(linha);
    });
    legenda.firstChild.setAttribute("aria-hidden", "true");
    alvo.replaceChildren(moldura, legenda);
    alvo.setAttribute("aria-label", "Mapa de calor do Brasil: refeições potenciais por UF e município de quem recebeu. " +
      "Maior UF: " + formato.format(maximo) + " refeições. Os números estão na tabela abaixo.");

    /* dica ao passar o mouse ou tocar */
    var atual = null;
    function mostrar(uf, evento) {
      var r = linhas[uf] || {}, u = geo.ufs.filter(function (x) { return x.uf === uf; })[0];
      if (atual) atual.classList.remove("is-ativo");
      atual = estados.querySelector('[data-uf="' + uf + '"]');
      atual.classList.add("is-ativo");
      estados.appendChild(atual);  // borda em destaque por cima das vizinhas
      var kg = (r.kg_medido || 0) + (r.kg_estimado || 0);
      dica.replaceChildren();
      [[uf + " · " + (u ? u.nome : ""), "b"],
       [formato.format(r.refeicoes_estimadas || 0) + " refeições potenciais"],
       [formatoKg.format(kg) + " kg (" + formatoKg.format(r.kg_medido || 0) + " físicos, " + formatoKg.format(r.kg_estimado || 0) + " estimados)"],
       [(r.ongs || 0) + ((r.ongs || 0) === 1 ? " ONG recebeu" : " ONGs receberam")]].forEach(function (l) {
        var linha = document.createElement(l[1] || "span"); linha.textContent = l[0]; dica.appendChild(linha);
      });
      dica.hidden = false;
      var caixa = moldura.getBoundingClientRect();
      var x = evento.clientX - caixa.left, y = evento.clientY - caixa.top;
      var largura = dica.offsetWidth, altura = dica.offsetHeight;
      dica.style.left = Math.max(4, Math.min(caixa.width - largura - 4, x - largura / 2)) + "px";
      dica.style.top = (y - altura - 14 < 4 ? y + 18 : y - altura - 14) + "px";
    }
    function esconder() { dica.hidden = true; if (atual) atual.classList.remove("is-ativo"); atual = null; }
    estados.addEventListener("pointermove", function (e) { if (e.target.dataset.uf) mostrar(e.target.dataset.uf, e); });
    estados.addEventListener("pointerdown", function (e) { if (e.target.dataset.uf) mostrar(e.target.dataset.uf, e); });
    svg.addEventListener("pointerleave", function (e) { if (e.pointerType === "mouse") esconder(); });
    moldura.addEventListener("pointerdown", function (e) { if (!e.target.dataset || !e.target.dataset.uf) esconder(); });
    alvo._esconder = esconder;

    /* calor e tamanho dos rótulos acompanham a largura real */
    var ultimaLargura = 0;
    function ajustar() {
      var largura = moldura.clientWidth;
      if (!largura || Math.abs(largura - ultimaLargura) < 2) return;
      ultimaLargura = largura;
      var fonte = Math.max(10, Math.min(13, largura / 52)) * LARGURA / largura;
      rotulos.setAttribute("font-size", fonte.toFixed(1));
      fundo.setAttribute("font-size", (fonte * 0.85).toFixed(1));
      pintarCalor(canvas, geo, dados, largura);
    }
    ajustar();
    if (alvo._observador) alvo._observador.disconnect();
    if (window.ResizeObserver) {
      alvo._observador = new ResizeObserver(function () { window.requestAnimationFrame(ajustar); });
      alvo._observador.observe(moldura);
    }
  }

  // tocar fora do mapa também fecha a dica
  document.addEventListener("pointerdown", function (e) {
    document.querySelectorAll(".mapa-calor").forEach(function (a) { if (a._esconder && !a.contains(e.target)) a._esconder(); });
  });

  /* desenha (ou redesenha) o mapa; devolve uma promessa */
  function desenhar(alvo, entrada) {
    return carregarMalha().then(function (geo) { montar(alvo, geo, entrada); });
  }

  window.ReConectaMapa = { desenhar: desenhar };
})();

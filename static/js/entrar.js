/* ReConecta — entrar: login por e-mail, CNPJ ou CPF.
   A validação aqui é só para a experiência; o servidor é a fonte da verdade. */
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }
  function digitos(valor) { return String(valor || "").replace(/\D+/g, ""); }

  function el(tag, attrs, filhos) {
    var no = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === "texto") no.textContent = attrs[k];
        else if (k === "classe") no.className = attrs[k];
        else no.setAttribute(k, attrs[k]);
      });
    }
    (filhos || []).forEach(function (f) {
      if (f == null || f === "") return;
      no.appendChild(typeof f === "string" ? document.createTextNode(f) : f);
    });
    return no;
  }

  var form = $("form-entrar");
  var identInput = $("identificador");
  var senhaInput = $("senha");
  var btnEntrar = $("btn-entrar");
  var btnOlho = $("btn-olho");
  var aviso = $("aviso-entrar");

  /* ---------- destino pós-login (?proximo= só caminho da mesma origem) ---------- */

  function destino() {
    /* O navegador remove tabulações e quebras de linha ao interpretar a URL e
       trata "\" como "/" em http(s), então a decisão usa a URL já normalizada:
       só caminho interno da própria origem — outro host, esquema ou
       protocol-relative (//site) voltam para /painel. */
    var p = new URLSearchParams(location.search).get("proximo") || "";
    if (p.charAt(0) !== "/" || /[\x00-\x20\x7f\\]/.test(p)) return "/painel";
    try {
      var alvo = new URL(p, location.origin);
      if (alvo.origin === location.origin && alvo.protocol === location.protocol) {
        return alvo.pathname + alvo.search + alvo.hash;
      }
    } catch (e) { /* URL inválida: cai no retorno interno abaixo */ }
    return "/painel";
  }

  /* ---------- já logado? ---------- */

  // reaproveita a consulta de sessão que o layout.js já fez (evita um GET /auth/me repetido)
  ((window.ReConecta && window.ReConecta.sessaoResposta) ||
    requisitar("/reconecta/auth/me", { headers: { "Accept": "application/json" } }))
    .then(function (r) { if (r.status === 200) location.replace(destino()); })
    .catch(function () { /* offline: deixa o formulário tentar e mostrar o erro */ });

  /* ---------- máscara do identificador ---------- */

  function mascaraCPF(d) {
    return d.slice(0, 11)
      .replace(/^(\d{3})(\d)/, "$1.$2")
      .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d)/, ".$1-$2");
  }

  function mascaraCNPJ(d) {
    return d.slice(0, 14)
      .replace(/^(\d{2})(\d)/, "$1.$2")
      .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d)/, ".$1/$2")
      .replace(/(\d{4})(\d)/, "$1-$2");
  }

  /* Só mascara quando o campo tem só dígitos e pontuação de máscara
     (qualquer letra ou @ transforma em e-mail e o texto fica livre). */
  function reaplicarMascaraIdentificador() {
    var v = identInput.value;
    if (/[^\d.\-\/]/.test(v)) return; // modo e-mail
    var d = digitos(v);
    if (!d) return;
    var mascarado = d.length <= 11 ? mascaraCPF(d) : mascaraCNPJ(d);
    if (mascarado !== v) {
      var pos = identInput.selectionStart || mascarado.length;
      var antes = digitos(v.slice(0, pos)).length;
      identInput.value = mascarado;
      var novaPos = 0, contados = 0;
      while (novaPos < mascarado.length && contados < antes) {
        if (/\d/.test(mascarado.charAt(novaPos))) contados++;
        novaPos++;
      }
      identInput.setSelectionRange(novaPos, novaPos);
    }
  }

  identInput.addEventListener("input", reaplicarMascaraIdentificador);

  /* ---------- mostrar/ocultar senha ---------- */

  btnOlho.addEventListener("click", function () {
    var mostrar = senhaInput.type === "password";
    senhaInput.type = mostrar ? "text" : "password";
    btnOlho.setAttribute("aria-pressed", mostrar ? "true" : "false");
    btnOlho.setAttribute("aria-label", mostrar ? "Ocultar senha" : "Mostrar senha");
    senhaInput.focus();
  });

  /* ---------- erros e avisos ---------- */

  function mostrarErro(input, mensagem) {
    var alvo = $(input.id + "-erro");
    if (mensagem) {
      input.setAttribute("aria-invalid", "true");
      if (alvo) alvo.textContent = mensagem;
    } else {
      input.removeAttribute("aria-invalid");
      if (alvo) alvo.textContent = "";
    }
  }

  function esconderAviso() { aviso.hidden = true; aviso.replaceChildren(); }

  function icone() {
    var span = el("span", { classe: "aviso__icone", "aria-hidden": "true" });
    span.innerHTML = '<svg viewBox="0 0 24 24" focusable="false" width="100%" height="100%">' +
      '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.8"/>' +
      '<path d="M5.8 18.2 18.2 5.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
    return span;
  }

  function mostrarAviso(titulo, texto, opcoes) {
    opcoes = opcoes || {};
    aviso.replaceChildren();
    aviso.className = "aviso" + (opcoes.erro ? " aviso--erro" : "");
    var corpo = el("div", null, [
      el("p", { classe: "aviso__titulo", texto: titulo }),
      texto ? el("p", { classe: "aviso__texto", texto: texto }) : null
    ]);
    if (opcoes.acao) {
      var b = el("button", { type: "button", classe: "btn btn--secundario btn--pequeno", texto: opcoes.acao.rotulo });
      b.addEventListener("click", opcoes.acao.fn);
      corpo.appendChild(b);
    }
    aviso.append(icone(), corpo);
    aviso.hidden = false;
  }

  function carregando(sim) {
    btnEntrar.classList.toggle("is-carregando", sim);
    btnEntrar.setAttribute("aria-busy", sim ? "true" : "false");
    btnEntrar.disabled = sim;
  }

  /* ---------- HTTP ---------- */

  function requisitar(url, opcoes) {
    opcoes = opcoes || {};
    opcoes.credentials = "same-origin";
    return fetch(url, opcoes).then(function (resp) {
      return resp.text().then(function (texto) {
        var corpo = null;
        try { corpo = texto ? JSON.parse(texto) : null; } catch (e) { corpo = null; }
        return { status: resp.status, ok: resp.ok, corpo: corpo || {} };
      });
    });
  }

  /* ---------- submit ---------- */

  [identInput, senhaInput].forEach(function (i) {
    i.addEventListener("input", function () { mostrarErro(i, ""); esconderAviso(); });
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    esconderAviso();
    mostrarErro(identInput, "");
    mostrarErro(senhaInput, "");

    var falhas = false;
    if (!identInput.value.trim()) {
      mostrarErro(identInput, "Informe seu e-mail, CNPJ ou CPF.");
      falhas = true;
    }
    if (!senhaInput.value) {
      mostrarErro(senhaInput, "Informe sua senha.");
      falhas = true;
    }
    if (falhas) { (identInput.getAttribute("aria-invalid") ? identInput : senhaInput).focus(); return; }

    carregando(true);
    requisitar("/reconecta/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({
        identificador: identInput.value.trim(),
        senha: senhaInput.value
      })
    }).then(function (r) {
      var c = r.corpo;
      if (r.status === 200) { location.assign(destino()); return; }
      if (r.status === 401) {
        mostrarAviso("Não foi possível entrar", c.mensagem || "E-mail, CNPJ/CPF ou senha incorretos.", { erro: true });
      } else if (r.status === 429) {
        mostrarAviso("Muitas tentativas", c.mensagem || "Aguarde alguns minutos e tente de novo.", { erro: true });
        identInput.focus();
      } else if (r.status === 400) {
        var mapa = { identificador: identInput, senha: senhaInput };
        var primeiro = null;
        Object.keys(c.campos || {}).forEach(function (nome) {
          if (mapa[nome]) { mostrarErro(mapa[nome], c.campos[nome]); if (!primeiro) primeiro = mapa[nome]; }
        });
        if (!primeiro) mostrarAviso("Confira os dados", c.mensagem, { erro: true });
        else primeiro.focus();
      } else {
        mostrarAviso("Algo deu errado", c.mensagem || "Tente novamente em alguns instantes.", {
          erro: true, acao: { rotulo: "Tentar novamente", fn: function () { form.requestSubmit(); } }
        });
      }
    }).catch(function () {
      mostrarAviso("Não conseguimos falar com o servidor", "Verifique sua conexão e tente de novo.", {
        acao: { rotulo: "Tentar novamente", fn: function () { form.requestSubmit(); } }
      });
    }).then(function () { carregando(false); });
  });
})();

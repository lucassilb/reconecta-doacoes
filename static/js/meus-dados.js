/* ReConecta — bloco "Meus dados e privacidade" do painel (LGPD).
   Exporta os dados da conta em JSON e exclui a conta por anonimização. */
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }
  var bloco = $("bloco-privacidade");
  if (!bloco) return;
  var consentInfo = $("consent-info"), aviso = $("aviso-privacidade");
  var btnExportar = $("btn-exportar-dados"), btnExcluir = $("btn-excluir-conta");

  function el(tag, attrs, filhos) {
    var no = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v == null) return;
      if (k === "texto") no.textContent = v;
      else if (k === "classe") no.className = v;
      else no.setAttribute(k, v);
    });
    (filhos || []).forEach(function (f) {
      if (f == null) return;
      no.appendChild(typeof f === "string" ? document.createTextNode(f) : f);
    });
    return no;
  }
  function mostrarAviso(titulo, texto, erro) {
    aviso.className = "aviso" + (erro ? " aviso--erro" : "");
    aviso.replaceChildren(el("div", null, [
      el("p", { classe: "aviso__titulo", texto: titulo }),
      texto ? el("p", { classe: "aviso__texto", texto: texto }) : null
    ]));
    aviso.hidden = false;
  }
  function requisitar(url, metodo) {
    return fetch(url, { method: metodo || "GET", credentials: "same-origin",
      headers: { "Accept": "application/json" } }).then(function (r) {
      return r.text().then(function (t) {
        var c = null;
        try { c = t ? JSON.parse(t) : null; } catch (e) { c = null; }
        return { status: r.status, ok: r.ok, corpo: c || {} };
      });
    });
  }
  function dataHora(iso) {
    var R = window.ReConecta, d = R && R.dataBrasilia ? R.dataBrasilia(iso) : null;
    return d ? d.toLocaleString("pt-BR", { timeZone: R.fuso, day: "2-digit", month: "2-digit",
      year: "numeric", hour: "2-digit", minute: "2-digit" }) : "";
  }

  ((window.ReConecta && window.ReConecta.sessaoResposta) || requisitar("/reconecta/auth/me"))
    .then(function (r) { return r && r.status === 200 ? r.corpo : null; })
    .then(function (u) {
      if (!u || !u.tipo) return;
      bloco.hidden = false;
      var c = u.consentimento || {};
      consentInfo.textContent = c.versao
        ? "Política de Privacidade aceita: versão " + c.versao + (c.em ? ", em " + dataHora(c.em) : "") + "."
        : "Sua conta foi criada antes da Política de Privacidade; ela vale para todos os usuários da mesma forma.";
    }).catch(function () { /* sem sessão: o painel já redireciona */ });

  btnExportar.addEventListener("click", function () {
    btnExportar.disabled = true;
    requisitar("/reconecta/auth/me/dados").then(function (r) {
      if (!r.ok) { mostrarAviso("Não foi possível exportar", (r.corpo || {}).mensagem || "Tente de novo em instantes.", true); return; }
      var blob = new Blob([JSON.stringify(r.corpo, null, 2)], { type: "application/json" });
      var a = el("a", { href: URL.createObjectURL(blob), download: "reconecta-meus-dados.json" });
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000);
      mostrarAviso("Dados exportados", "O arquivo JSON com seus dados foi baixado.");
    }).catch(function () {
      mostrarAviso("Não conseguimos falar com o servidor", "Verifique sua conexão e tente de novo.", true);
    }).then(function () { btnExportar.disabled = false; });
  });

  btnExcluir.addEventListener("click", function () {
    var confirmado = window.confirm(
      "Excluir sua conta?\n\n" +
      "Seus dados pessoais (nome, documento, e-mail, telefone e endereço) são apagados agora. " +
      "Pedidos e doações continuam existindo só como estatística, sem identificação. " +
      "Esta ação não pode ser desfeita.");
    if (!confirmado) return;
    btnExcluir.disabled = true;
    requisitar("/reconecta/auth/me", "DELETE").then(function (r) {
      if (r.status === 204) {
        location.replace("/");
        return;
      }
      mostrarAviso("Não foi possível excluir", (r.corpo || {}).mensagem || "Tente de novo em instantes.", true);
    }).catch(function () {
      mostrarAviso("Não conseguimos falar com o servidor", "Verifique sua conexão e tente de novo.", true);
    }).then(function () { btnExcluir.disabled = false; });
  });
})();

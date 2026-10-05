/* ReConecta — lista pública de ações de arrecadação (/arrecadacoes). */
(function () {
  "use strict";
  var R = window.RCArrecadacao, el = R.el;
  var alvo = document.getElementById("arr-conteudo");

  function vazio() {
    return el("div", { classe: "arr-vazio" }, [
      el("h3", { texto: "Nenhuma ação de arrecadação aberta agora" }),
      el("p", { texto: "Quando uma empresa abrir uma ação, ela aparece aqui com as categorias aceitas, o prazo e a cidade de entrega." }),
      el("a", { classe: "btn btn--secundario", href: "/#doacoes" }, ["Ver doações disponíveis"])
    ]);
  }

  function carregar() {
    alvo.setAttribute("aria-busy", "true");
    R.requisitar("/reconecta/arrecadacoes").then(function (r) {
      var lista = Array.isArray(r.corpo) ? r.corpo : [];
      if (!r.ok) throw new Error("HTTP " + r.status);
      alvo.replaceChildren(lista.length
        ? el("ul", { classe: "acoes", "aria-label": R.plural(lista.length, "ação aberta", "ações abertas") },
            lista.map(function (a) { return el("li", null, [R.cartaoAcao(a)]); }))
        : vazio());
    }).catch(function () {
      var b = el("button", { type: "button", classe: "btn btn--secundario btn--pequeno", texto: "Tentar novamente" });
      b.addEventListener("click", carregar);
      alvo.replaceChildren(el("div", { classe: "aviso", role: "alert" }, [el("p", { texto: "Não conseguimos carregar as ações agora." }), b]));
    }).then(function () { alvo.setAttribute("aria-busy", "false"); });
  }

  /* empresa logada: atalho para criar ação no painel; doador: só doa */
  document.addEventListener("reconecta:sessao", function (e) {
    var u = e.detail && e.detail.usuario;
    var cta = document.getElementById("arr-cta");
    cta.replaceChildren();
    if (u && u.tipo === "empresa") {
      cta.append(el("a", { classe: "btn btn--primario", href: "/painel#acoes" }, ["Criar uma ação", R.icone("seta", "btn__seta")]));
      cta.hidden = false;
    } else if (!u) {
      cta.append(el("a", { classe: "btn btn--secundario", href: "/cadastro" }, ["Cadastrar para participar"]));
      cta.hidden = false;
    } else {
      cta.hidden = true;
    }
  });

  carregar();
})();

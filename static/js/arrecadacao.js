/* ReConecta — detalhe da ação de arrecadação e questionário curto de doação.
   O servidor é a fonte da verdade; a validação aqui só adianta o que ele vai conferir. */
(function () {
  "use strict";
  var R = window.RCArrecadacao, el = R.el;
  function $(id) { return document.getElementById(id); }

  var m = location.pathname.match(/\/arrecadacoes\/(\d+)/);
  var ID = m ? m[1] : null;
  var acao = null;

  var PERGUNTAS = [
    ["dentro_validade", "O alimento está dentro da validade?"],
    ["embalagem_ok", "A embalagem está fechada e sem danos (ou, se for in natura, sem sinais de estrago)?"],
    ["armazenado_ok", "Foi guardado do jeito certo (geladeira ou congelador quando precisa)?"],
    ["nao_caseiro", "Não é comida feita em casa?"]
  ];
  var AVISO_NAO = {
    dentro_validade: "Alimento fora da validade não pode ser doado.",
    embalagem_ok: "Só aceitamos embalagem fechada e sem danos, ou alimento in natura sem estrago.",
    armazenado_ok: "O alimento precisa ter sido guardado do jeito certo.",
    nao_caseiro: "Por segurança, comida feita em casa não pode ser doada."
  };
  var TIPOS_FOTO = ["image/jpeg", "image/png", "image/webp"];
  var MAX_FOTO = 5 * 1024 * 1024;

  /* ---------- carregar a ação ---------- */

  function mostrarErroCarga(titulo, texto) {
    $("det-carregando").hidden = true;
    var e = $("det-erro");
    e.replaceChildren(el("p", { classe: "aviso__titulo", texto: titulo }), el("p", { texto: texto }),
      el("a", { classe: "btn btn--secundario btn--pequeno", href: "/arrecadacoes" }, ["Ver ações abertas"]));
    e.hidden = false;
  }

  function preencher(a) {
    acao = a;
    document.title = a.titulo + " · Ação de arrecadação · ReConecta";
    $("det-titulo").textContent = a.titulo;
    $("det-empresa").replaceChildren(R.icone("loja", "det__empresa-icone"), el("span", null, ["Organizada por ",
      el("strong", { texto: R.nome(a.empresa && a.empresa.nome) }),
      a.empresa && a.empresa.municipio_uf ? " · " + R.local(a.empresa.municipio_uf) : ""]));
    $("det-descricao").textContent = a.descricao;
    if (a.meta_descricao) { $("det-meta").textContent = a.meta_descricao; $("det-meta-bloco").hidden = false; }
    $("det-periodo").textContent = R.dataCurta(a.data_inicio) + " a " + R.dataLonga(a.data_fim) + " (" + R.prazoTexto(a.data_fim) + ")";
    $("det-entrega").textContent = a.entrega && a.entrega.municipio_uf
      ? R.local(a.entrega.municipio_uf) + ". O endereço completo aparece depois que a doação é confirmada."
      : "O endereço aparece depois que a doação é confirmada.";
    var n = Number(a.contribuicoes_aceitas) || 0;
    $("det-contagem").textContent = R.plural(n, "doação aceita", "doações aceitas");
    $("det-categorias").replaceChildren(R.chipsCategorias(a.categorias));

    // categorias do questionário: só as aceitas pela ação
    var sel = $("c-categoria");
    sel.replaceChildren(el("option", { value: "", texto: "Escolha" }));
    (a.categorias || []).forEach(function (c) { sel.appendChild(el("option", { value: c, texto: c })); });

    estadoInicial(a);
    $("det-carregando").hidden = true;
    $("det").hidden = false;
  }

  /* pode_contribuir só vem para quem está logado */
  function estadoInicial(a) {
    var logado = a.pode_contribuir !== undefined;
    var encerrada = a.status && a.status !== "ATIVA";
    $("btn-abrir").hidden = true; $("link-entrar").hidden = true; $("doar-bloqueio").hidden = true; $("doar-cadastro").hidden = true;
    if (encerrada) {
      $("doar-bloqueio").textContent = "Esta ação foi encerrada e não recebe mais doações.";
      $("doar-bloqueio").hidden = false;
    } else if (!logado) {
      $("link-entrar").href = "/entrar?proximo=" + encodeURIComponent("/arrecadacoes/" + a.id);
      $("link-entrar").hidden = false;
      $("doar-cadastro").hidden = false;
    } else if (a.pode_contribuir) {
      $("btn-abrir").hidden = false;
    } else {
      $("doar-bloqueio").textContent = a.motivo_bloqueio || "Você não pode doar para esta ação.";
      $("doar-bloqueio").hidden = false;
    }
  }

  function carregar() {
    if (!ID) { mostrarErroCarga("Ação não encontrada", "O endereço desta página está incompleto."); return; }
    Promise.all([
      R.requisitar("/reconecta/arrecadacoes/" + ID),
      R.requisitar("/reconecta/publico/opcoes").catch(function () { return { ok: false, corpo: {} }; })
    ]).then(function (rs) {
      var r = rs[0], op = rs[1];
      var un = $("c-unidade");
      un.replaceChildren(el("option", { value: "", texto: "Escolha" }));
      ((op.ok && op.corpo.unidades) || ["kg", "g", "L", "unidade", "pacote", "caixa"]).forEach(function (u) {
        un.appendChild(el("option", { value: u, texto: u }));
      });
      if (r.status === 404) { mostrarErroCarga("Ação não encontrada", "Ela pode ter sido removida ou o endereço está errado."); return; }
      if (!r.ok) throw new Error("HTTP " + r.status);
      preencher(r.corpo);
    }).catch(function () {
      mostrarErroCarga("Não conseguimos carregar esta ação", "Verifique sua conexão e recarregue a página.");
    });
  }

  /* ---------- questionário ---------- */

  function montarPerguntas() {
    var alvo = $("quest-perguntas");
    PERGUNTAS.forEach(function (p, i) {
      var chave = p[0];
      var aviso = el("p", { classe: "pergunta__aviso", id: "q-" + chave + "-aviso", "aria-live": "polite" });
      function opcao(valor, rotulo) {
        var input = el("input", { type: "radio", name: chave, value: valor, classe: "pergunta__radio", id: "q-" + chave + "-" + valor });
        input.addEventListener("change", function () {
          aviso.textContent = valor === "nao" ? AVISO_NAO[chave] + " Com essa resposta a doação não será aceita." : "";
          fs.classList.toggle("pergunta--nao", valor === "nao");
          fs.classList.remove("pergunta--erro");
        });
        return el("label", { classe: "pergunta__opcao pergunta__opcao--" + valor, "for": input.id }, [input, el("span", { texto: rotulo })]);
      }
      var fs = el("fieldset", { classe: "pergunta", id: "q-" + chave, "aria-describedby": "q-" + chave + "-aviso" }, [
        el("legend", { classe: "pergunta__texto" }, [el("span", { classe: "pergunta__n", "aria-hidden": "true", texto: String(i + 1) }), p[1]]),
        el("div", { classe: "pergunta__opcoes" }, [opcao("sim", "Sim"), opcao("nao", "Não")]),
        aviso
      ]);
      alvo.appendChild(fs);
    });
  }

  var fotoUrl = null;
  function atualizarFoto() {
    var input = $("c-foto"), f = input.files && input.files[0];
    var previa = $("c-foto-previa");
    if (fotoUrl) { URL.revokeObjectURL(fotoUrl); fotoUrl = null; }
    erroCampo("foto", "");
    if (!f) { $("c-foto-nome").textContent = "Tirar ou escolher foto"; previa.classList.remove("foto__previa--img"); previa.style.backgroundImage = ""; return; }
    $("c-foto-nome").textContent = f.name.length > 40 ? f.name.slice(0, 37) + "…" : f.name;
    if (TIPOS_FOTO.indexOf(f.type) !== -1) {
      fotoUrl = URL.createObjectURL(f);
      previa.style.backgroundImage = "url(\"" + fotoUrl + "\")";
      previa.classList.add("foto__previa--img");
    }
    var msg = validarFoto(f);
    if (msg) erroCampo("foto", msg);
  }
  function validarFoto(f) {
    if (!f) return "Mande uma foto do alimento.";
    if (TIPOS_FOTO.indexOf(f.type) === -1) return "A foto precisa ser JPEG, PNG ou WebP.";
    if (f.size > MAX_FOTO) return "A foto pode ter no máximo 5 MB.";
    return "";
  }

  var CAMPO_INPUT = { alimento: "c-alimento", categoria: "c-categoria", quantidade: "c-quantidade", unidade_medida: "c-unidade", validade: "c-validade", foto: "c-foto" };
  function erroCampo(campo, msg) {
    var id = CAMPO_INPUT[campo];
    if (id) {
      var input = $(id), p = $(id + "-erro");
      if (msg) input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid");
      if (p) p.textContent = msg || "";
      return input;
    }
    var fs = $("q-" + campo);
    if (fs) {
      fs.classList.toggle("pergunta--erro", !!msg);
      if (msg) $("q-" + campo + "-aviso").textContent = msg;
      return fs.querySelector("input");
    }
    return null;
  }
  function limparErros() {
    Object.keys(CAMPO_INPUT).forEach(function (c) { erroCampo(c, ""); });
    PERGUNTAS.forEach(function (p) { $("q-" + p[0]).classList.remove("pergunta--erro"); });
    esconderAviso();
  }

  function resposta(chave) {
    var r = document.querySelector('input[name="' + chave + '"]:checked');
    return r ? r.value : "";
  }

  function validar() {
    var c = {};
    var alimento = $("c-alimento").value.trim();
    if (alimento.length < 2) c.alimento = "Diga qual é o alimento.";
    if (!$("c-categoria").value) c.categoria = "Escolha a categoria.";
    var q = Number(String($("c-quantidade").value).replace(",", "."));
    if (!$("c-quantidade").value.trim() || isNaN(q) || q <= 0) c.quantidade = "A quantidade precisa ser maior que zero.";
    if (!$("c-unidade").value) c.unidade_medida = "Escolha a unidade.";
    var v = $("c-validade").value;
    if (!v) c.validade = "Informe a validade.";
    else if (v < R.hojeISO()) c.validade = "Alimento vencido não pode ser doado.";
    PERGUNTAS.forEach(function (p) { if (!resposta(p[0])) c[p[0]] = "Responda sim ou não."; });
    var fm = validarFoto($("c-foto").files && $("c-foto").files[0]);
    if (fm) c.foto = fm;
    return c;
  }

  function aplicarCampos(campos) {
    var primeiro = null;
    Object.keys(campos).forEach(function (k) {
      var i = erroCampo(k, campos[k]);
      if (i && !primeiro) primeiro = i;
    });
    if (primeiro) primeiro.focus();
    if (Object.keys(campos).length && !primeiro) mostrarAviso("Confira os dados", [Object.values(campos)[0]], false);
  }

  function mostrarAviso(titulo, linhas, recusa) {
    var a = $("quest-aviso");
    a.className = "quest__aviso" + (recusa ? " quest__aviso--recusa" : "");
    a.replaceChildren(el("p", { classe: "quest__aviso-titulo", texto: titulo }),
      el("ul", null, linhas.map(function (l) { return el("li", { texto: l }); })),
      recusa ? el("p", { classe: "quest__aviso-rodape", texto: "Nada foi registrado. Se for possível corrigir, ajuste as respostas e tente de novo." }) : null);
    a.hidden = false;
    a.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  function esconderAviso() { $("quest-aviso").hidden = true; $("quest-aviso").replaceChildren(); }

  function abrir() {
    $("doar-inicio").hidden = true;
    $("form-contribuicao").hidden = false;
    $("c-alimento").focus();
  }
  function cancelar() {
    $("form-contribuicao").hidden = true;
    $("doar-inicio").hidden = false;
    $("doar-titulo").focus();
  }

  function enviar(e) {
    e.preventDefault();
    limparErros();
    var campos = validar();
    if (Object.keys(campos).length) { aplicarCampos(campos); return; }

    var fd = new FormData();
    fd.append("alimento", $("c-alimento").value.trim());
    fd.append("categoria", $("c-categoria").value);
    fd.append("quantidade", String(Number(String($("c-quantidade").value).replace(",", "."))));
    fd.append("unidade_medida", $("c-unidade").value);
    fd.append("validade", $("c-validade").value);
    PERGUNTAS.forEach(function (p) { fd.append(p[0], resposta(p[0])); });
    fd.append("foto", $("c-foto").files[0]);

    var btn = $("btn-doar");
    btn.disabled = true; btn.classList.add("is-carregando");
    R.requisitar("/reconecta/arrecadacoes/" + ID + "/contribuicoes", { method: "POST", form: fd }).then(function (r) {
      var c = r.corpo;
      if (r.status === 201) { confirmar(c); return; }
      if (r.status === 422) {
        var motivos = (c.motivos || []).map(function (mo) { return mo.mensagem; });
        mostrarAviso("Desta vez a doação não pode ser aceita", motivos.length ? motivos : [c.mensagem || "O alimento não atende às regras desta ação."], true);
      } else if (r.status === 400 && c.campos) {
        aplicarCampos(c.campos);
      } else if (r.status === 401) {
        location.href = "/entrar?proximo=" + encodeURIComponent("/arrecadacoes/" + ID);
      } else if (r.status === 409 || r.status === 403) {
        mostrarAviso("Não foi possível doar para esta ação", [c.mensagem || "Esta ação não aceita a sua doação."], false);
      } else {
        mostrarAviso("Não foi possível concluir", [c.mensagem || "Tente novamente em alguns instantes."], false);
      }
    }).catch(function () {
      mostrarAviso("Não conseguimos falar com o servidor", ["Verifique sua conexão e tente de novo."], false);
    }).then(function () { btn.disabled = false; btn.classList.remove("is-carregando"); });
  }

  function confirmar(c) {
    var ent = c.entrega || {};
    $("ok-endereco").textContent = ent.endereco || "O endereço está em Minhas contribuições, no painel.";
    $("ok-prazo").textContent = R.dataLonga(ent.data_fim || (acao && acao.data_fim));
    $("form-contribuicao").hidden = true;
    $("doar-ok").hidden = false;
    $("doar-ok").focus();
    if (acao) {
      var n = (Number(acao.contribuicoes_aceitas) || 0) + 1;
      acao.contribuicoes_aceitas = n;
      $("det-contagem").textContent = R.plural(n, "doação aceita", "doações aceitas");
    }
  }

  montarPerguntas();
  // o erro de um campo some assim que a pessoa mexe nele
  Object.keys(CAMPO_INPUT).forEach(function (c) {
    if (c === "foto") return;
    var i = $(CAMPO_INPUT[c]);
    ["input", "change"].forEach(function (ev) { i.addEventListener(ev, function () { if (i.getAttribute("aria-invalid")) erroCampo(c, ""); }); });
  });
  $("c-validade").min = R.hojeISO();
  $("c-foto").addEventListener("change", atualizarFoto);
  $("btn-abrir").addEventListener("click", abrir);
  $("btn-cancelar").addEventListener("click", cancelar);
  $("form-contribuicao").addEventListener("submit", enviar);
  carregar();
})();

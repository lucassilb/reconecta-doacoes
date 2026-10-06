/* ReConecta — painel: empresa publica e gerencia doações; doador vê a rede.
   O servidor é a fonte da verdade; a validação local só melhora a experiência. */
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }
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

  function requisitar(url, opcoes) {
    opcoes = opcoes || {};
    opcoes.credentials = "same-origin";
    opcoes.headers = Object.assign({ "Accept": "application/json" }, opcoes.headers || {});
    return fetch(url, opcoes).then(function (resp) {
      return resp.text().then(function (texto) {
        var corpo = null;
        try { corpo = texto ? JSON.parse(texto) : null; } catch (e) { corpo = null; }
        return { status: resp.status, ok: resp.ok, corpo: corpo || {} };
      });
    });
  }

  function postJson(url, dados) {
    return requisitar(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(dados)
    });
  }

  /* ---------- erros/avisos ---------- */

  function mostrarErro(input, mensagem) {
    var alvo = input && input.closest(".campo") && input.closest(".campo").querySelector("[data-erro]");
    if (input && input.id) alvo = alvo || $(input.id + "-erro");
    if (mensagem) {
      if (input) input.setAttribute("aria-invalid", "true");
      if (alvo) alvo.textContent = mensagem;
    } else {
      if (input) input.removeAttribute("aria-invalid");
      if (alvo) alvo.textContent = "";
    }
  }

  function iconeAviso(tipo) {
    var paths = {
      alerta: '<path d="M12 3.5 2.8 19.5h18.4z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 10v4.2" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><circle cx="12" cy="17" r="1.1" fill="currentColor"/>',
      bloqueio: '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M5.8 18.2 18.2 5.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
      ok: '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8.5 12.4l2.4 2.4 4.6-5" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>'
    };
    var span = el("span", { classe: "aviso__icone", "aria-hidden": "true" });
    span.innerHTML = '<svg viewBox="0 0 24 24" focusable="false" width="100%" height="100%">' + paths[tipo] + "</svg>";
    return span;
  }

  function mostrarAviso(caixa, titulo, texto, opcoes) {
    opcoes = opcoes || {};
    caixa.replaceChildren();
    caixa.className = "aviso" + (opcoes.erro ? " aviso--erro" : "") + (opcoes.ok ? " aviso--ok" : "");
    var corpo = el("div", null, [
      el("p", { classe: "aviso__titulo", texto: titulo }),
      texto ? el("p", { classe: "aviso__texto", texto: texto }) : null
    ]);
    if (opcoes.acao) {
      var b = el("button", { type: "button", classe: "btn btn--secundario btn--pequeno", texto: opcoes.acao.rotulo });
      b.addEventListener("click", opcoes.acao.fn);
      corpo.appendChild(b);
    }
    caixa.append(iconeAviso(opcoes.ok ? "ok" : opcoes.erro ? "bloqueio" : "alerta"), corpo);
    caixa.hidden = false;
  }

  function esconderAviso(caixa) { caixa.hidden = true; caixa.replaceChildren(); }

  /* ---------- datas ---------- */

  function hojeISO() {
    return window.ReConecta.diaISO(new Date());
  }

  function fmtDataHora(iso) {
    var d = window.ReConecta.dataBrasilia(iso);
    if (!d) return String(iso || "");
    return d.toLocaleString("pt-BR", { timeZone: window.ReConecta.fuso, day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function fmtData(iso) {
    var d = window.ReConecta.dataBrasilia(iso);
    if (!d) return String(iso || "");
    return d.toLocaleDateString("pt-BR", { timeZone: window.ReConecta.fuso });
  }

  function telefone(t) {
    // (11) 98765-4321 ou (11) 4196-9800; ver formatarTelefone em layout.js
    return (window.ReConecta && window.ReConecta.formatarTelefone) ? window.ReConecta.formatarTelefone(t) : t;
  }

  var PLURAL_UN = { unidade: "unidades", pacote: "pacotes", caixa: "caixas" };
  function fmtQtd(q, unidade) {
    var n = Number(q);
    var txt = isNaN(n) ? String(q) : n.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
    var u = unidade || "";
    if (PLURAL_UN[u] && n !== 1) u = PLURAL_UN[u];
    return (txt + " " + u).trim();
  }

  /* ---------- sessão ---------- */

  var carregando = $("painel-carregando");
  var corpo = $("painel-corpo");

  // reaproveita a consulta de sessão que o layout.js já fez (evita um GET /auth/me repetido)
  ((window.ReConecta && window.ReConecta.sessaoResposta) || requisitar("/reconecta/auth/me"))
    .then(function (r) {
      if (r.status === 401) {
        location.replace("/entrar?proximo=/painel");
        return null;
      }
      if (!r.ok) throw new Error("me " + r.status);
      return r.corpo;
    })
    .then(function (u) {
      if (!u) return;
      carregando.hidden = true;
      corpo.hidden = false;
      if (u.tipo === "empresa") iniciarEmpresa(u); else iniciarDoador(u);
    })
    .catch(function () {
      carregando.replaceChildren(el("p", { texto: "Não conseguimos falar com o servidor. Recarregue a página em instantes." }));
    });

  function saudacao(u, rotulo) {
    $("saudacao-tipo").textContent = rotulo;
    // sem caixa alta da Receita: "ARCOS DOURADOS ..." → "Olá, Arcos"
    var nome = (window.ReConecta && window.ReConecta.nomeTitulo) ? window.ReConecta.nomeTitulo(u.nome) : String(u.nome || "");
    $("saudacao-nome").textContent = "Olá, " + nome.split(" ")[0];
    var selo = $("saudacao-selo");
    selo.textContent = u.tipo === "empresa" ? "Empresa" : "Doador";
  }

  function dlDados(dl, pares) {
    dl.replaceChildren();
    pares.forEach(function (p) {
      if (p[1] == null || p[1] === "") return;
      dl.append(el("dt", { texto: p[0] }), el("dd", { texto: p[1] }));
    });
  }

  /* ================= MEUS DADOS (editar: PUT /reconecta/auth/me) ================= */

  /* Empresa altera e-mail e telefone (nome, CNPJ e endereço vêm da Receita);
     doador altera nome, e-mail e telefone (CPF fixo). Troca de senha é opcional.
     Envia só o que mudou; o servidor repete as regras do cadastro. */

  var MSG_DADOS = {
    nome: "Informe seu nome completo (de 3 a 100 caracteres).",
    email: "Informe um e-mail válido, como nome@dominio.com.",
    telefone: "Informe o telefone com DDD (10 ou 11 dígitos).",
    senhaAtual: "Informe sua senha atual para trocar a senha.",
    senha: "A nova senha precisa de pelo menos 8 caracteres, com letra e número.",
    confirmar: "As senhas não são iguais.",
    emailUsado: "Este e-mail já está em uso em outra conta."
  };

  function digitos(v) { return String(v || "").replace(/\D+/g, ""); }
  function emailValido(v) { v = String(v).trim(); return v.length <= 100 && /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v); }
  function telefoneValido(v) { var n = digitos(v).length; return n === 10 || n === 11; }
  function senhaValida(v) { return v.length >= 8 && /[A-Za-zÀ-ÖØ-öø-ÿ]/.test(v) && /\d/.test(v); }
  function nivelSenha(v) {
    if (!v) return 0;
    if (!senhaValida(v)) return 1;
    if (v.length >= 12 && /[^A-Za-zÀ-ÖØ-öø-ÿ\d]/.test(v)) return 3;
    return 2;
  }
  function mascaraTelefone(v) {
    var d = digitos(v);
    if (d.length > 11 && d.charAt(0) === "0") d = d.slice(1);
    d = d.slice(0, 11);
    if (d.length <= 2) return d.length ? "(" + d : "";
    var ddd = d.slice(0, 2), resto = d.slice(2);
    var corte = d.length === 11 ? 5 : 4;
    if (resto.length <= corte) return "(" + ddd + ") " + resto;
    return "(" + ddd + ") " + resto.slice(0, corte) + "-" + resto.slice(corte);
  }

  function paresDados(u) {
    if (u.tipo === "empresa") {
      return [
        ["Empresa", u.nome],
        ["CNPJ", u.cnpj_formatado],
        ["Endereço", u.endereco],
        ["E-mail", u.email],
        ["Telefone", telefone(u.telefone)]
      ];
    }
    return [
      ["Nome", u.nome],
      ["CPF", u.cpf_formatado],
      ["E-mail", u.email],
      ["Telefone", telefone(u.telefone)]
    ];
  }

  function campoDados(id, rotulo, input, ajuda) {
    input.id = id;
    input.classList.add("campo__entrada");
    var desc = [ajuda ? id + "-ajuda" : null, id + "-erro"].filter(Boolean).join(" ");
    input.setAttribute("aria-describedby", desc);
    return el("div", { classe: "campo" }, [
      el("label", { for: id, classe: "campo__rotulo", texto: rotulo }),
      input,
      ajuda ? el("p", { id: id + "-ajuda", classe: "campo__ajuda", texto: ajuda }) : null,
      el("p", { id: id + "-erro", classe: "campo__erro", "data-erro": "" })
    ]);
  }

  function iniciarMeusDados(u) {
    var t = u.tipo === "empresa" ? "empresa" : "doador";
    var dl = $("dados-" + t);
    var form = $("form-dados-" + t);
    var btnEditar = $("editar-" + t);
    var aviso = $("aviso-dados-" + t);
    var atual = u;
    var entradas = {};

    dlDados(dl, paresDados(atual));

    function entrada(nome, tipoInput, attrs) {
      var i = el("input", Object.assign({ type: tipoInput, name: nome }, attrs || {}));
      entradas[nome] = i;
      return i;
    }

    /* ---- monta o formulário uma vez ---- */
    var p = "ed-" + t + "-";
    var grade = el("div", { classe: "form-dados__grade" });
    if (t === "doador") {
      grade.appendChild(campoDados(p + "nome", "Nome completo", entrada("nome", "text", { autocomplete: "name", maxlength: "100", required: "" })));
    }
    grade.appendChild(campoDados(p + "email", "E-mail", entrada("email", "email", { autocomplete: "email", maxlength: "100", inputmode: "email", required: "" })));
    grade.appendChild(campoDados(p + "telefone", "Telefone", entrada("telefone", "tel", { autocomplete: "tel", inputmode: "tel", maxlength: "16", placeholder: "(11) 98765-4321", required: "" })));

    var medidor = el("div", { classe: "senha-forca", "aria-hidden": "true" }, [el("i"), el("i"), el("i")]);
    var campoNova = campoDados(p + "nova", "Nova senha", entrada("nova_senha", "password", { autocomplete: "new-password", maxlength: "72" }), "Pelo menos 8 caracteres, com letra e número.");
    campoNova.insertBefore(medidor, campoNova.querySelector(".campo__ajuda"));
    var mostrar = el("input", { type: "checkbox", id: p + "mostrar" });
    var blocoSenha = el("details", { classe: "form-dados__senha" }, [
      el("summary", { texto: "Trocar senha (opcional)" }),
      el("div", { classe: "form-dados__grade" }, [
        campoDados(p + "atual", "Senha atual", entrada("senha_atual", "password", { autocomplete: "current-password", maxlength: "72" })),
        campoNova,
        campoDados(p + "confirmar", "Confirmar nova senha", entrada("confirmar", "password", { autocomplete: "new-password", maxlength: "72" }))
      ]),
      el("label", { classe: "form-dados__mostrar", for: p + "mostrar" }, [mostrar, " Mostrar senhas"])
    ]);
    var avisoForm = el("div", { classe: "aviso", role: "alert", hidden: "" });
    var btnSalvar = el("button", { type: "submit", classe: "btn btn--primario", texto: "Salvar" });
    var btnCancelar = el("button", { type: "button", classe: "btn btn--secundario", texto: "Cancelar" });

    form.append(
      el("p", { classe: "campo__ajuda", texto: t === "empresa"
        ? "Nome, CNPJ e endereço vêm da Receita Federal e não podem ser alterados aqui."
        : "O CPF não pode ser alterado." }),
      grade, blocoSenha, avisoForm,
      el("div", { classe: "form-dados__acoes" }, [btnSalvar, btnCancelar])
    );

    entradas.telefone.addEventListener("input", function () {
      entradas.telefone.value = mascaraTelefone(entradas.telefone.value);
    });
    entradas.nova_senha.addEventListener("input", function () {
      medidor.setAttribute("data-nivel", String(nivelSenha(entradas.nova_senha.value)));
    });
    mostrar.addEventListener("change", function () {
      ["senha_atual", "nova_senha", "confirmar"].forEach(function (n) { entradas[n].type = mostrar.checked ? "text" : "password"; });
    });
    // o erro some quando a pessoa corrige o campo
    Object.keys(entradas).forEach(function (n) {
      entradas[n].addEventListener("input", function () {
        if (entradas[n].getAttribute("aria-invalid")) mostrarErro(entradas[n], "");
      });
    });

    function limparErros() {
      Object.keys(entradas).forEach(function (n) { mostrarErro(entradas[n], ""); });
      esconderAviso(avisoForm);
    }

    function preencher() {
      if (entradas.nome) entradas.nome.value = atual.nome || "";
      entradas.email.value = atual.email || "";
      entradas.telefone.value = mascaraTelefone(atual.telefone || "");
      ["senha_atual", "nova_senha", "confirmar"].forEach(function (n) { entradas[n].value = ""; entradas[n].type = "password"; });
      mostrar.checked = false;
      medidor.setAttribute("data-nivel", "0");
      blocoSenha.open = false;
      limparErros();
    }

    function abrir() {
      preencher();
      esconderAviso(aviso);
      dl.hidden = true;
      form.hidden = false;
      btnEditar.hidden = true;
      btnEditar.setAttribute("aria-expanded", "true");
      (entradas.nome || entradas.email).focus();
    }

    function fechar() {
      form.hidden = true;
      dl.hidden = false;
      btnEditar.hidden = false;
      btnEditar.setAttribute("aria-expanded", "false");
      btnEditar.focus();
    }

    btnEditar.addEventListener("click", abrir);
    btnCancelar.addEventListener("click", fechar);
    form.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !btnSalvar.disabled) { e.preventDefault(); fechar(); }
    });

    /* corpo só com o que mudou; erros locais por campo */
    function montarCorpo(erros) {
      var corpo = {};
      if (entradas.nome) {
        var nome = entradas.nome.value.trim().replace(/\s+/g, " ");
        if (nome.length < 3 || nome.length > 100) erros.nome = MSG_DADOS.nome;
        else if (nome !== atual.nome) corpo.nome = nome;
      }
      var email = entradas.email.value.trim();
      if (!emailValido(email)) erros.email = MSG_DADOS.email;
      else if (email.toLowerCase() !== String(atual.email || "").toLowerCase()) corpo.email = email;
      var tel = digitos(entradas.telefone.value);
      if (!telefoneValido(tel)) erros.telefone = MSG_DADOS.telefone;
      else if (tel !== digitos(atual.telefone)) corpo.telefone = tel;

      var sa = entradas.senha_atual.value, ns = entradas.nova_senha.value, cf = entradas.confirmar.value;
      if (sa || ns || cf) {
        if (!sa) erros.senha_atual = MSG_DADOS.senhaAtual;
        if (!senhaValida(ns)) erros.nova_senha = MSG_DADOS.senha;
        if (cf !== ns) erros.confirmar = MSG_DADOS.confirmar;
        corpo.senha_atual = sa;
        corpo.nova_senha = ns;
      }
      return corpo;
    }

    function aplicarErrosDados(campos) {
      var primeiro = null;
      Object.keys(campos).forEach(function (n) {
        var i = entradas[n];
        if (!i) return;
        if (n === "senha_atual" || n === "nova_senha" || n === "confirmar") blocoSenha.open = true;
        var m = campos[n];
        mostrarErro(i, Array.isArray(m) ? m.join(" ") : String(m));
        if (!primeiro) primeiro = i;
      });
      if (primeiro) primeiro.focus();
      return primeiro;
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      limparErros();
      var erros = {};
      var corpo = montarCorpo(erros);
      if (Object.keys(erros).length) {
        aplicarErrosDados(erros);
        mostrarAviso(avisoForm, "Confira os campos destacados.", "", { erro: true });
        return;
      }
      if (!Object.keys(corpo).length) {
        mostrarAviso(avisoForm, "Nada para salvar.", "Você não alterou nenhum dado.");
        return;
      }

      var trocouSenha = "nova_senha" in corpo;
      btnSalvar.disabled = true; btnCancelar.disabled = true;
      btnSalvar.classList.add("is-carregando");
      btnSalvar.textContent = "Salvando…";

      requisitar("/reconecta/auth/me", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corpo)
      }).then(function (r) {
        if (r.status === 401) { location.replace("/entrar?proximo=/painel"); return; }
        if (r.ok) {
          atual = r.corpo && r.corpo.tipo ? r.corpo : Object.assign({}, atual, corpo);
          dlDados(dl, paresDados(atual));
          saudacao(atual, t === "empresa" ? "Painel da empresa" : "Painel do doador");
          if (window.ReConecta && window.ReConecta.atualizarSessao) window.ReConecta.atualizarSessao(); // "Olá, …" no cabeçalho
          fechar();
          mostrarAviso(aviso, "Dados atualizados.",
            trocouSenha ? "Sua senha foi trocada. Use a nova senha no próximo login." : "As alterações já valem para o seu acesso.",
            { ok: true });
          return;
        }
        var c = r.corpo || {};
        if (r.status === 409 || c.codigo === "EMAIL_JA_CADASTRADO") {
          aplicarErrosDados({ email: MSG_DADOS.emailUsado });
          mostrarAviso(avisoForm, "Não foi possível salvar.", MSG_DADOS.emailUsado, { erro: true });
          return;
        }
        var campos = c.campos && typeof c.campos === "object" ? c.campos : {};
        var achou = aplicarErrosDados(campos);
        mostrarAviso(avisoForm, "Não foi possível salvar.",
          achou ? "Confira os campos destacados." : (c.mensagem || "Tente novamente em instantes."),
          { erro: true });
      }).catch(function () {
        mostrarAviso(avisoForm, "Sem conexão com o servidor.", "Seus dados não foram alterados. Tente novamente.", {
          erro: true,
          acao: { rotulo: "Tentar novamente", fn: function () { form.requestSubmit(); } }
        });
      }).then(function () {
        btnSalvar.disabled = false; btnCancelar.disabled = false;
        btnSalvar.classList.remove("is-carregando");
        btnSalvar.textContent = "Salvar";
      });
    });
  }

  /* ================= EMPRESA ================= */

  var OPCOES = { categorias: [], unidades: [] };
  var listaItens;
  var linhasItens = [];

  function iniciarEmpresa(u) {
    saudacao(u, "Painel da empresa");
    $("bloco-empresa").hidden = false;

    iniciarMeusDados(u);

    iniciarDoacoes();
    carregarMinhasDoacoes();
  }

  /* Publicar pedido e "Meus pedidos": só empresa (rodada 9). */
  function iniciarDoacoes() {
    $("bloco-doacoes").hidden = false;
    listaItens = $("lista-itens");
    requisitar("/reconecta/publico/opcoes")
      .then(function (r) { if (r.ok) OPCOES = r.corpo; })
      .catch(function () {})
      .then(function () {
        adicionarItem();
        carregarDoacoes();
        if (location.hash === "#publicar") $("publicar-t").scrollIntoView({ block: "start" });
      });
  }

  /* ---------- itens do formulário ---------- */

  function campoItem(rotulo, nome, input) {
    return el("div", { classe: "campo item__" + nome }, [
      el("label", { classe: "campo__rotulo", "for": input.id || "", texto: rotulo }),
      input,
      el("p", { classe: "campo__erro", "data-erro": "" })
    ]);
  }

  function selectItem(nome, opcoesLista, placeholder) {
    var s = el("select", { classe: "campo__entrada", "data-campo": nome, id: "item-" + linhasItens.length + "-" + nome });
    s.appendChild(el("option", { value: "", texto: placeholder }));
    opcoesLista.forEach(function (o) { s.appendChild(el("option", { value: o, texto: o })); });
    return s;
  }

  function adicionarItem() {
    var i = linhasItens.length;
    var nome = el("input", { classe: "campo__entrada", "data-campo": "nome", id: "item-" + i + "-nome", maxlength: "100", type: "text" });
    var categoria = selectItem("categoria", OPCOES.categorias, "Categoria");
    var quantidade = el("input", { classe: "campo__entrada", "data-campo": "quantidade", id: "item-" + i + "-quantidade", inputmode: "decimal", type: "text", placeholder: "0" });
    var unidade = selectItem("unidade_medida", OPCOES.unidades, "Unid.");

    var linha = el("div", { classe: "item" });
    var grade = el("div", { classe: "item__grade" }, [
      campoItem("Item", "nome", nome),
      campoItem("Categoria", "categoria", categoria),
      campoItem("Qtd.", "quantidade", quantidade),
      campoItem("Unidade", "unidade", unidade)
    ]);
    var remover = el("button", {
      type: "button", classe: "item__remover", "aria-label": "Remover item"
    });
    remover.innerHTML = '<svg viewBox="0 0 16 16" focusable="false"><path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
    remover.addEventListener("click", function () {
      linha.remove();
      linhasItens = linhasItens.filter(function (l) { return l !== registro; });
    });

    linha.append(grade, remover);
    listaItens.appendChild(linha);

    var registro = { no: linha, campos: { nome: nome, categoria: categoria, quantidade: quantidade, unidade_medida: unidade } };
    linhasItens.push(registro);
    nome.focus();
  }

  /* ---------- validação do formulário ---------- */

  var limiteInput = $("limite");
  var avisoDoacao = $("aviso-doacao");

  function validarFormulario() {
    var campos = {};
    var limiteV = limiteInput.value;
    if (!limiteV) campos["data_limite_retirada"] = "Informe até quando você pode receber as doações.";
    else if (window.ReConecta.dataBrasilia(limiteV) <= new Date()) campos["data_limite_retirada"] = "A data precisa ser no futuro.";

    if (!linhasItens.length) campos["itens"] = "Adicione pelo menos um item ao pedido.";

    linhasItens.forEach(function (linha, i) {
      var f = linha.campos;
      if (!f.nome.value.trim()) campos["itens[" + i + "].nome"] = "Informe o nome do item.";
      if (!f.categoria.value) campos["itens[" + i + "].categoria"] = "Escolha uma categoria.";
      var q = Number(String(f.quantidade.value).replace(",", "."));
      if (!f.quantidade.value.trim() || isNaN(q) || q <= 0) campos["itens[" + i + "].quantidade"] = "Quantidade deve ser maior que zero.";
      if (!f.unidade_medida.value) campos["itens[" + i + "].unidade_medida"] = "Escolha a unidade.";
    });

    return campos;
  }

  function aplicarErros(campos) {
    var primeiro = null;
    Object.keys(campos).forEach(function (chave) {
      var input = null;
      if (chave === "data_limite_retirada") input = limiteInput;
      else if (chave === "itens") { var p = $("itens-erro"); p.textContent = campos[chave]; return; }
      else {
        var m = chave.match(/^itens\[(\d+)\]\.(\w+)$/);
        if (m && linhasItens[+m[1]]) input = linhasItens[+m[1]].campos[m[2]];
      }
      if (input) { mostrarErro(input, campos[chave]); if (!primeiro) primeiro = input; }
    });
    if (primeiro) primeiro.focus();
  }

  function limparErrosForm() {
    mostrarErro(limiteInput, "");
    $("itens-erro").textContent = "";
    linhasItens.forEach(function (l) {
      Object.keys(l.campos).forEach(function (c) { mostrarErro(l.campos[c], ""); });
    });
  }

  $("btn-add-item").addEventListener("click", adicionarItem);

  /* ---------- preencher o pedido com IA (modelo local gratuito; a empresa revisa antes de publicar) ---------- */

  function preencherComIA() {
    var texto = $("ia-texto").value.trim();
    var aviso = $("ia-aviso"), erro = $("ia-erro"), btn = $("btn-ia");
    erro.textContent = ""; $("ia-texto").removeAttribute("aria-invalid"); esconderAviso(aviso);
    if (texto.length < 5) { erro.textContent = "Escreva o que vocês precisam (por exemplo: 100 litros de leite e 50 pães até sexta)."; $("ia-texto").setAttribute("aria-invalid", "true"); $("ia-texto").focus(); return; }
    btn.disabled = true; btn.classList.add("is-carregando");
    postJson("/reconecta/ia/interpretar-pedido", { texto: texto }).then(function (r) {
      var c = r.corpo;
      if (r.status === 401) { location.replace("/entrar?proximo=/painel"); return; }
      if (r.status === 400 && c.campos && c.campos.texto) { erro.textContent = c.campos.texto; $("ia-texto").setAttribute("aria-invalid", "true"); return; }
      if (r.status === 429) { mostrarAviso(aviso, "Muitos pedidos seguidos", c.mensagem || "Aguarde um pouco e tente de novo.", { erro: true }); return; }
      if (!r.ok) { mostrarAviso(aviso, "Não foi possível interpretar o texto", c.mensagem || "Preencha os itens manualmente.", { erro: true }); return; }
      var itens = Array.isArray(c.itens) ? c.itens : [];
      if (!itens.length) {
        mostrarAviso(aviso, "Não encontramos itens no texto", "Tente citar quantidade e alimento (ex.: 100 pães) ou preencha os itens manualmente.", { erro: true });
        return;
      }
      // troca as linhas atuais pelas sugeridas
      linhasItens = []; listaItens.replaceChildren();
      itens.forEach(function (it) {
        adicionarItem();
        var f = linhasItens[linhasItens.length - 1].campos;
        f.nome.value = it.nome || "";
        if (OPCOES.categorias.indexOf(it.categoria) !== -1) f.categoria.value = it.categoria;
        f.quantidade.value = it.quantidade != null ? String(it.quantidade).replace(".", ",") : "";
        if (OPCOES.unidades.indexOf(it.unidade_medida) !== -1) f.unidade_medida.value = it.unidade_medida;
      });
      if (c.receber_ate) limiteInput.value = String(c.receber_ate).slice(0, 10) + "T18:00";
      var fonte = c.fonte === "llm" ? "Sugerido pelo modelo local gratuito " + (c.modelo || "") + "." : "Sugerido por regras automáticas (IA indisponível no momento).";
      var partes = [fonte, "Revise os itens, as categorias, as quantidades e o prazo antes de publicar."];
      if (!c.receber_ate) partes.push("O texto não trazia uma data: escolha o \"Receber até\".");
      if (c.observacoes) partes.push("Observação: " + c.observacoes);
      mostrarAviso(aviso, "Preenchemos " + itens.length + (itens.length === 1 ? " item" : " itens") + " a partir do texto", partes.join(" "), { ok: true });
      $("publicar-t").scrollIntoView({ block: "nearest" });
    }).catch(function () {
      mostrarAviso(aviso, "Não conseguimos falar com o servidor", "Verifique sua conexão ou preencha os itens manualmente.", { erro: true });
    }).then(function () { btn.disabled = false; btn.classList.remove("is-carregando"); });
  }
  $("btn-ia").addEventListener("click", preencherComIA);

  $("form-doacao").addEventListener("submit", function (e) {
    e.preventDefault();
    esconderAviso(avisoDoacao);
    limparErrosForm();
    var campos = validarFormulario();
    if (Object.keys(campos).length) { aplicarErros(campos); return; }

    var itens = linhasItens.map(function (l) {
      return {
        nome: l.campos.nome.value.trim(),
        categoria: l.campos.categoria.value,
        quantidade: Number(String(l.campos.quantidade.value).replace(",", ".")),
        unidade_medida: l.campos.unidade_medida.value
      };
    });

    var btn = $("btn-publicar");
    btn.classList.add("is-carregando");
    btn.disabled = true;
    var corpo = { data_limite_retirada: limiteInput.value, itens: itens };
    postJson("/reconecta/painel/doacoes", corpo).then(function (r) {
      var c = r.corpo;
      if (r.status === 201) {
        limparFormulario();
        carregarDoacoes();
        mostrarAviso(avisoDoacao, "Pedido publicado",
          "Ele já aparece em Doações disponíveis para quem quiser doar.", { ok: true });
        $("minhas-t").scrollIntoView({ behavior: "smooth", block: "nearest" });
        return;
      }
      if (r.status === 400 && c.campos) { aplicarErros(c.campos); return; }
      if (r.status === 403) {
        mostrarAviso(avisoDoacao, "Não foi possível publicar", c.mensagem || "Sua conta não tem permissão para publicar doações.", { erro: true });
      } else if (r.status === 401) {
        location.replace("/entrar?proximo=/painel");
      } else {
        mostrarAviso(avisoDoacao, "Não foi possível publicar", c.mensagem || "Tente novamente em alguns instantes.", { erro: true });
      }
    }).catch(function () {
      mostrarAviso(avisoDoacao, "Não conseguimos falar com o servidor", "Verifique sua conexão e tente de novo.", {
        acao: { rotulo: "Tentar novamente", fn: function () { $("form-doacao").requestSubmit(); } }
      });
    }).then(function () {
      btn.classList.remove("is-carregando");
      btn.disabled = false;
    });
  });

  function limparFormulario() {
    limiteInput.value = "";
    linhasItens = [];
    listaItens.replaceChildren();
    adicionarItem();
    limparErrosForm();
  }

  /* ---------- minhas doações ---------- */

  var SELOS = {
    DISPONIVEL: ["Aberto", ""],
    RESERVADA: ["Reservada", "selo--acento"],
    RETIRADA: ["Retirada", "selo--cinza"]
  };

  function carregarDoacoes() {
    var lista = $("lista-doacoes");
    lista.setAttribute("aria-busy", "true");
    requisitar("/reconecta/painel/doacoes").then(function (r) {
      if (r.status === 401) { location.replace("/entrar?proximo=/painel"); return; }
      lista.replaceChildren();
      if (!r.ok || !Array.isArray(r.corpo) || !r.corpo.length) {
        lista.appendChild(el("p", { classe: "doacoes__vazio", texto: "Nenhum pedido publicado ainda. Use o formulário acima para dizer do que você precisa." }));
        return;
      }
      r.corpo.forEach(function (d) { lista.appendChild(cartaoDoacao(d, true)); });
    }).catch(function () {
      lista.replaceChildren(el("p", { classe: "doacoes__vazio", texto: "Não foi possível carregar suas doações. Tente atualizar." }));
    }).then(function () { lista.setAttribute("aria-busy", "false"); });
  }

  function nomeTitulo(n) { return window.ReConecta && window.ReConecta.nomeTitulo ? window.ReConecta.nomeTitulo(n) : String(n || ""); }
  function receberAte(d) { return d.receber_ate || d.data_limite_retirada; }
  function localTitulo(mu) { var x = String(mu).split("/"); return nomeTitulo(x[0]) + (x[1] ? "/" + x[1].toUpperCase() : ""); }

  function linhaItem(i) {
    var meta = Number(i.quantidade) || 0;
    var temProgresso = i.recebido != null;
    var recebido = Number(i.recebido) || 0;
    var pct = meta > 0 ? Math.min(100, Math.round(recebido / meta * 100)) : 0;
    var texto = temProgresso ? fmtQtd(recebido, "") + " de " + fmtQtd(meta, i.unidade_medida) : fmtQtd(meta, i.unidade_medida);
    return el("li", { classe: "pedido-linha" }, [
      el("span", { classe: "pedido-linha__topo" }, [el("strong", { texto: i.nome }), el("span", { classe: "pedido-linha__qtd", texto: texto })]),
      temProgresso ? el("span", { classe: "pedido-linha__barra", role: "progressbar", "aria-label": "Recebido de " + i.nome,
        "aria-valuemin": "0", "aria-valuemax": String(meta), "aria-valuenow": String(Math.min(recebido, meta)), "aria-valuetext": texto }, [el("span", { style: "width:" + pct + "%" })]) : null
    ]);
  }

  function quemDoou(c) {
    var q = c.quem;
    if (q && typeof q === "object") q = q.nome;
    return nomeTitulo(q || (c.doador && c.doador.nome) || (c.empresa && c.empresa.nome) || "");
  }
  function nomeItem(c) { return (c.item && c.item.nome) || c.item_nome || c.alimento || "Item"; }
  function unidadeDe(c) { return c.unidade_medida || (c.item && c.item.unidade_medida) || ""; }

  function recebida(c) {
    return el("li", { classe: "recebida" }, [
      c.foto_url
        ? el("a", { classe: "recebida__foto", href: c.foto_url, target: "_blank", rel: "noopener" }, [
            el("img", { src: c.foto_url, alt: "Foto de " + nomeItem(c) + " enviada por " + quemDoou(c), width: "56", height: "56", loading: "lazy" })])
        : el("span", { classe: "recebida__foto", "aria-hidden": "true" }),
      el("div", { classe: "recebida__texto" }, [
        el("p", null, [el("strong", { texto: nomeItem(c) }), " · " + fmtQtd(c.quantidade, unidadeDe(c))]),
        el("p", { classe: "recebida__meta", texto: [quemDoou(c), c.validade ? "val. " + fmtData(c.validade) : "", c.criado_em ? "em " + fmtDataHora(c.criado_em) : ""].filter(Boolean).join(" · ") })
      ])
    ]);
  }

  function cartaoDoacao(d, propria) {
    var selo = SELOS[d.status] || null;
    var art = el("article", { classe: "doacao" });
    var emp = d.empresa || d.estabelecimento || {};
    art.appendChild(el("div", { classe: "doacao__topo" }, [
      el("p", { classe: "doacao__onde" }, [nomeTitulo(emp.nome) || "Pedido",
        emp.municipio_uf ? el("span", { classe: "doacao__uf", texto: " · " + localTitulo(emp.municipio_uf) }) : null]),
      selo ? el("span", { classe: "selo " + selo[1], texto: selo[0] }) : null
    ]));
    art.appendChild(el("p", { classe: "doacao__prazo", texto: "Receber até " + fmtDataHora(receberAte(d)) }));
    if (d.itens && d.itens.length) art.appendChild(el("ul", { classe: "pedido-itens-painel" }, d.itens.map(linhaItem)));

    var recebidas = Array.isArray(d.contribuicoes) ? d.contribuicoes : (Array.isArray(d.doacoes_recebidas) ? d.doacoes_recebidas : []);
    if (propria) {
      art.appendChild(recebidas.length
        ? el("details", { classe: "doacao__recebidas", open: recebidas.length <= 4 }, [
            el("summary", { texto: "Doações recebidas (" + recebidas.length + ")" }),
            el("ul", null, recebidas.map(recebida))
          ])
        : el("p", { classe: "doacao__sem", texto: "Ainda não chegou nenhuma doação para este pedido." }));
    } else {
      art.appendChild(el("a", { classe: "btn btn--primario btn--pequeno doacao__doar", href: "/doacoes/" + d.id }, ["Doar para este pedido"]));
    }

    if (propria && d.status === "DISPONIVEL") {
      var acoes = el("div", { classe: "doacao__acoes", "aria-live": "polite" });
      var btnRemover = el("button", { type: "button", classe: "btn btn--perigo btn--pequeno", texto: "Remover" });

      btnRemover.addEventListener("click", function () {
        // referências diretas: o texto da pergunta não entra em .children
        var btnSim = el("button", { type: "button", classe: "btn btn--perigo btn--pequeno", texto: "Sim, remover" });
        var btnCancelar = el("button", { type: "button", classe: "link-seta", texto: "Cancelar" });
        var confirma = el("span", { classe: "doacao__confirmar", role: "group", "aria-label": "Confirmar remoção" }, [
          "Remover esta doação? ", btnSim, btnCancelar
        ]);
        btnSim.addEventListener("click", function () {
          btnSim.disabled = true; btnCancelar.disabled = true;
          btnSim.classList.add("is-carregando");
          removerDoacao(d.id, acoes, btnRemover);
        });
        btnCancelar.addEventListener("click", function () {
          acoes.replaceChildren(btnRemover);
          btnRemover.focus();
        });
        acoes.replaceChildren(confirma);
        btnCancelar.focus();
      });

      acoes.appendChild(btnRemover);
      art.appendChild(acoes);
    }
    return art;
  }

  function removerDoacao(id, acoes, btnRemover) {
    function falha(msg) {
      acoes.replaceChildren(el("p", { classe: "campo__erro", role: "alert", texto: msg }), btnRemover);
    }
    requisitar("/reconecta/painel/doacoes/" + id, { method: "DELETE" }).then(function (r) {
      if (r.status === 204) { carregarDoacoes(); return; }
      if (r.status === 401) { location.replace("/entrar?proximo=/painel"); return; }
      if (r.status === 409) {
        falha((r.corpo.mensagem ? r.corpo.mensagem + " " : "") +
          "Só dá para remover doações ainda disponíveis e sem reserva.");
      } else if (r.status === 404) {
        falha("Esta doação não foi encontrada; ela pode já ter sido removida. Atualize a lista.");
      } else {
        falha(r.corpo.mensagem || "Não foi possível remover. Tente novamente.");
      }
    }).catch(function () {
      falha("Sem conexão com o servidor. Tente novamente.");
    });
  }

  $("btn-recarregar").addEventListener("click", carregarDoacoes);

  /* ================= DOADOR ================= */

  function iniciarDoador(u) {
    saudacao(u, "Painel do doador");
    $("bloco-doador").hidden = false;
    $("bloco-rede").hidden = false;

    iniciarMeusDados(u);
    carregarMinhasDoacoes();

    requisitar("/reconecta/publico/resumo").then(function (r) {
      if (!r.ok) return;
      var c = r.corpo;
      var resumo = $("resumo");
      resumo.replaceChildren(
        resumoNumero(c.empresas, "empresas"),
        resumoNumero(c.doadores, "doadores"),
        resumoNumero(c.doacoes_disponiveis, "pedidos abertos"),
        resumoNumero(c.doacoes_recebidas, "doações recebidas")
      );
    }).catch(function () {});

    var lista = $("lista-disponiveis");
    requisitar("/reconecta/publico/doacoes?limite=8").then(function (r) {
      lista.replaceChildren();
      if (!r.ok || !Array.isArray(r.corpo) || !r.corpo.length) {
        lista.appendChild(el("p", { classe: "doacoes__vazio", texto: "Nenhum pedido aberto agora. Quando uma empresa publicar, ele aparece aqui." }));
        return;
      }
      r.corpo.forEach(function (d) { lista.appendChild(cartaoDoacao(d, false)); });
    }).catch(function () {
      lista.replaceChildren(el("p", { classe: "doacoes__vazio", texto: "Não foi possível carregar as doações. Recarregue a página." }));
    });
  }

  /* ---------- minhas doações: o que a pessoa doou (doador e empresa) ---------- */

  function cartaoMinhaDoacao(c) {
    var ped = c.doacao || c.pedido || {};
    var emp = typeof ped.empresa === "string" ? { nome: ped.empresa } : (ped.empresa || {});
    var ent = c.entrega || {};
    var STATUS = { ACEITA: ["Aceita", ""], ENTREGUE: ["Entregue", "selo--cinza"], CANCELADA: ["Cancelada", "selo--acento"] };
    var st = STATUS[c.status] || STATUS.ACEITA;
    var ate = ent.receber_ate || ped.receber_ate || ped.data_limite_retirada;
    return el("article", { classe: "doacao minha-doacao" }, [
      c.foto_url ? el("img", { classe: "minha-doacao__foto", src: c.foto_url, alt: "Foto enviada de " + nomeItem(c), width: "64", height: "64", loading: "lazy" }) : null,
      el("div", { classe: "minha-doacao__texto" }, [
        el("div", { classe: "doacao__topo" }, [
          el("p", { classe: "doacao__onde" }, [nomeItem(c) + " · " + fmtQtd(c.quantidade, unidadeDe(c))]),
          el("span", { classe: "selo " + st[1], texto: st[0] })
        ]),
        el("p", { classe: "doacao__prazo" }, ["Para ", ped.id ? el("a", { href: "/doacoes/" + ped.id, texto: nomeTitulo(emp.nome) || "o pedido" }) : (nomeTitulo(emp.nome) || "o pedido")]),
        ent.endereco ? el("p", { classe: "doacao__retirada" }, [el("strong", { texto: "Entregar em: " }), ent.endereco]) : null,
        ate ? el("p", { classe: "doacao__prazo", texto: "Até " + fmtDataHora(ate) }) : null
      ])
    ]);
  }

  function carregarMinhasDoacoes() {
    $("bloco-minhas-doacoes").hidden = false;
    var lista = $("lista-minhas-doacoes");
    lista.setAttribute("aria-busy", "true");
    requisitar("/reconecta/painel/minhas-doacoes").then(function (r) {
      lista.replaceChildren();
      var itens = r.ok && Array.isArray(r.corpo) ? r.corpo : [];
      if (!itens.length) {
        lista.appendChild(el("p", { classe: "doacoes__vazio" }, ["Você ainda não doou para nenhum pedido. ", el("a", { href: "/#doacoes", texto: "Veja as doações disponíveis" }), "."]));
        return;
      }
      itens.forEach(function (c) { lista.appendChild(cartaoMinhaDoacao(c)); });
    }).catch(function () {
      lista.replaceChildren(el("p", { classe: "doacoes__vazio", texto: "Não foi possível carregar suas doações." }));
    }).then(function () {
      lista.setAttribute("aria-busy", "false");
      if (location.hash === "#minhas-doacoes") $("minhas-doacoes").scrollIntoView({ block: "start" });
    });
  }

  function resumoNumero(n, rotulo) {
    return el("li", { classe: "metrica" }, [
      el("span", { classe: "metrica__valor", texto: n == null ? "—" : String(n) }),
      el("span", { classe: "metrica__rotulo", texto: rotulo })
    ]);
  }
})();

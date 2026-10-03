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
    var d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  function fmtDataHora(iso) {
    var d = new Date(iso);
    if (isNaN(d)) return String(iso || "");
    return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function fmtData(iso) {
    var d = new Date(iso + "T12:00:00");
    if (isNaN(d)) return String(iso || "");
    return d.toLocaleDateString("pt-BR");
  }

  function telefone(t) {
    // (11) 98765-4321 ou (11) 4196-9800; ver formatarTelefone em layout.js
    return (window.ReConecta && window.ReConecta.formatarTelefone) ? window.ReConecta.formatarTelefone(t) : t;
  }

  function fmtQtd(q, unidade) {
    var n = Number(q);
    var txt = isNaN(n) ? String(q) : n.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
    return txt + " " + (unidade || "");
  }

  /* ---------- sessão ---------- */

  var carregando = $("painel-carregando");
  var corpo = $("painel-corpo");

  requisitar("/reconecta/auth/me")
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

  /* ================= EMPRESA ================= */

  var OPCOES = { categorias: [], unidades: [] };
  var listaItens;
  var linhasItens = [];

  function iniciarEmpresa(u) {
    saudacao(u, "Painel da empresa");
    $("bloco-empresa").hidden = false;

    dlDados($("dados-empresa"), [
      ["Empresa", u.nome],
      ["CNPJ", u.cnpj_formatado],
      ["Endereço", u.endereco],
      ["E-mail", u.email],
      ["Telefone", telefone(u.telefone)]
    ]);

    iniciarDoacoes(false);
  }

  /* Publicar e "Minhas doações": comum a empresa e doador. O doador informa o
     local de retirada (não tem endereço no cadastro); a empresa usa o da Receita. */
  var ehDoador = false;
  function iniciarDoacoes(doador) {
    ehDoador = doador;
    $("bloco-doacoes").hidden = false;
    var grupo = $("grupo-retirada");
    grupo.hidden = !doador;
    grupo.disabled = !doador;
    listaItens = $("lista-itens");
    requisitar("/reconecta/publico/opcoes")
      .then(function (r) { if (r.ok) OPCOES = r.corpo; })
      .catch(function () {})
      .then(function () {
        adicionarItem();
        carregarDoacoes();
      });
  }

  var UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split(" ");
  var retiradaInputs = {
    "retirada.endereco": $("retirada-endereco"),
    "retirada.municipio": $("retirada-municipio"),
    "retirada.uf": $("retirada-uf")
  };
  function validarRetirada(campos) {
    if (!ehDoador) return;
    var end = retiradaInputs["retirada.endereco"].value.trim();
    var mun = retiradaInputs["retirada.municipio"].value.trim();
    var uf = retiradaInputs["retirada.uf"].value;
    if (end.length < 5) campos["retirada.endereco"] = "Informe o endereço de retirada (rua e número).";
    if (mun.length < 2) campos["retirada.municipio"] = "Informe a cidade.";
    if (UFS.indexOf(uf) === -1) campos["retirada.uf"] = "Escolha a UF.";
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
    var validade = el("input", { classe: "campo__entrada campo__entrada--mono", "data-campo": "validade", id: "item-" + i + "-validade", type: "date", min: hojeISO() });

    var linha = el("div", { classe: "item" });
    var grade = el("div", { classe: "item__grade" }, [
      campoItem("Item", "nome", nome),
      campoItem("Categoria", "categoria", categoria),
      campoItem("Qtd.", "quantidade", quantidade),
      campoItem("Unidade", "unidade", unidade),
      campoItem("Validade", "validade", validade)
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

    var registro = { no: linha, campos: { nome: nome, categoria: categoria, quantidade: quantidade, unidade_medida: unidade, validade: validade } };
    linhasItens.push(registro);
    nome.focus();
  }

  /* ---------- validação do formulário ---------- */

  var limiteInput = $("limite");
  var avisoDoacao = $("aviso-doacao");

  function validarFormulario() {
    var campos = {};
    var limiteV = limiteInput.value;
    var limiteOk = false;
    if (!limiteV) {
      campos["data_limite_retirada"] = "Informe até quando a doação pode ser retirada.";
    } else if (new Date(limiteV) <= new Date()) {
      campos["data_limite_retirada"] = "A retirada precisa ser no futuro.";
    } else {
      limiteOk = true;
    }

    if (!linhasItens.length) campos["itens"] = "Adicione pelo menos um item à doação.";

    var menorVal = null;
    linhasItens.forEach(function (linha, i) {
      var f = linha.campos;
      if (!f.nome.value.trim()) campos["itens[" + i + "].nome"] = "Informe o nome do item.";
      if (!f.categoria.value) campos["itens[" + i + "].categoria"] = "Escolha uma categoria.";
      var q = Number(String(f.quantidade.value).replace(",", "."));
      if (!f.quantidade.value.trim() || isNaN(q) || q <= 0) campos["itens[" + i + "].quantidade"] = "Quantidade deve ser maior que zero.";
      if (!f.unidade_medida.value) campos["itens[" + i + "].unidade_medida"] = "Escolha a unidade.";
      var v = f.validade.value;
      if (!v) campos["itens[" + i + "].validade"] = "Informe a validade.";
      else if (v < hojeISO()) campos["itens[" + i + "].validade"] = "A validade não pode estar no passado.";
      else if (menorVal === null || v < menorVal) menorVal = v;
    });

    validarRetirada(campos);
    if (limiteOk && menorVal && limiteV.slice(0, 10) > menorVal) {
      campos["data_limite_retirada"] = "A retirada não pode ser depois da menor validade dos itens (" + fmtData(menorVal) + ").";
    }
    return campos;
  }

  function aplicarErros(campos) {
    var primeiro = null;
    Object.keys(campos).forEach(function (chave) {
      var input = null;
      if (chave === "data_limite_retirada") input = limiteInput;
      else if (retiradaInputs[chave]) input = retiradaInputs[chave];
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
    Object.keys(retiradaInputs).forEach(function (k) { mostrarErro(retiradaInputs[k], ""); });
    $("itens-erro").textContent = "";
    linhasItens.forEach(function (l) {
      Object.keys(l.campos).forEach(function (c) { mostrarErro(l.campos[c], ""); });
    });
  }

  $("btn-add-item").addEventListener("click", adicionarItem);

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
        unidade_medida: l.campos.unidade_medida.value,
        validade: l.campos.validade.value
      };
    });

    var btn = $("btn-publicar");
    btn.classList.add("is-carregando");
    btn.disabled = true;
    var corpo = { data_limite_retirada: limiteInput.value, itens: itens };
    if (ehDoador) corpo.retirada = {
      endereco: retiradaInputs["retirada.endereco"].value.trim(),
      municipio: retiradaInputs["retirada.municipio"].value.trim(),
      uf: retiradaInputs["retirada.uf"].value
    };
    postJson("/reconecta/painel/doacoes", corpo).then(function (r) {
      var c = r.corpo;
      if (r.status === 201) {
        limparFormulario();
        carregarDoacoes();
        mostrarAviso(avisoDoacao, "Doação publicada",
          "Ela já aparece na lista pública de doações.", { ok: true });
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
    DISPONIVEL: ["Disponível", ""],
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
        lista.appendChild(el("p", { classe: "doacoes__vazio", texto: "Nenhuma doação publicada ainda. Quando sobrar alimento bom, publique aqui." }));
        return;
      }
      r.corpo.forEach(function (d) { lista.appendChild(cartaoDoacao(d, true)); });
    }).catch(function () {
      lista.replaceChildren(el("p", { classe: "doacoes__vazio", texto: "Não foi possível carregar suas doações. Tente atualizar." }));
    }).then(function () { lista.setAttribute("aria-busy", "false"); });
  }

  function cartaoDoacao(d, propria) {
    var selo = SELOS[d.status] || null;
    var art = el("article", { classe: "doacao" });

    var pf = d.origem === "doador" || (!d.estabelecimento && d.doador);
    var quem = pf ? (d.doador || {}) : (d.estabelecimento || {});
    var onde = el("p", { classe: "doacao__onde" }, [
      quem.nome || "Doação",
      quem.municipio_uf ? el("span", { classe: "doacao__uf", texto: " · " + quem.municipio_uf }) : null,
      pf ? el("span", { classe: "selo selo--pf", texto: "Pessoa física" }) : null
    ]);

    art.appendChild(el("div", { classe: "doacao__topo" }, [
      onde,
      selo ? el("span", { classe: "selo " + selo[1], texto: selo[0] }) : null
    ]));

    art.appendChild(el("p", {
      classe: "doacao__prazo",
      texto: "Retirar até " + fmtDataHora(d.data_limite_retirada)
    }));
    if (propria && d.retirada && d.retirada.endereco) {
      art.appendChild(el("p", { classe: "doacao__retirada" }, [
        el("strong", { texto: "Local de retirada: " }),
        d.retirada.endereco + ", " + d.retirada.municipio + "/" + d.retirada.uf
      ]));
    }

    if (d.itens && d.itens.length) {
      art.appendChild(el("ul", { classe: "doacao__itens" }, d.itens.map(function (i) {
        var validade = i.validade ? " · val. " + fmtData(i.validade) : "";
        return el("li", { classe: "doacao__item", texto: i.nome + " — " + fmtQtd(i.quantidade, i.unidade_medida) + validade });
      })));
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

    dlDados($("dados-doador"), [
      ["Nome", u.nome],
      ["CPF", u.cpf_formatado],
      ["E-mail", u.email],
      ["Telefone", telefone(u.telefone)]
    ]);
    iniciarDoacoes(true);

    requisitar("/reconecta/publico/resumo").then(function (r) {
      if (!r.ok) return;
      var c = r.corpo;
      var resumo = $("resumo");
      resumo.replaceChildren(
        resumoNumero(c.empresas, "empresas"),
        resumoNumero(c.doadores, "doadores"),
        resumoNumero(c.doacoes_disponiveis, "doações abertas"),
        resumoNumero(c.kg_disponiveis != null ? Number(c.kg_disponiveis).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) : "—", "kg disponíveis")
      );
    }).catch(function () {});

    var lista = $("lista-disponiveis");
    requisitar("/reconecta/publico/doacoes?limite=8").then(function (r) {
      lista.replaceChildren();
      if (!r.ok || !Array.isArray(r.corpo) || !r.corpo.length) {
        lista.appendChild(el("p", { classe: "doacoes__vazio", texto: "Nenhuma doação disponível agora. Quando alguém publicar, aparece aqui." }));
        return;
      }
      r.corpo.forEach(function (d) { lista.appendChild(cartaoDoacao(d, false)); });
    }).catch(function () {
      lista.replaceChildren(el("p", { classe: "doacoes__vazio", texto: "Não foi possível carregar as doações. Recarregue a página." }));
    });
  }

  function resumoNumero(n, rotulo) {
    return el("li", { classe: "metrica" }, [
      el("span", { classe: "metrica__valor", texto: n == null ? "—" : String(n) }),
      el("span", { classe: "metrica__rotulo", texto: rotulo })
    ]);
  }
})();

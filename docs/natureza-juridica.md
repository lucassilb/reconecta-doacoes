# Natureza jurídica e perfil de ONG

O cadastro de CNPJ usa a **Tabela de Natureza Jurídica 2021 do CONCLA/IBGE**. Consideramos `ong` apenas os códigos abaixo, desde que a situação cadastral seja ativa. A classificação indica uma forma jurídica apta; não certifica atuação em assistência alimentar. Uma organização que também possua CNAE alimentar recebe os dois perfis.

| Código | Natureza jurídica | Decisão |
| --- | --- | --- |
| 3069 | Fundação Privada | ONG |
| 3204 | Estabelecimento, no Brasil, de Fundação ou Associação Estrangeiras | ONG |
| 3220 | Organização Religiosa | ONG |
| 3239 | Comunidade Indígena | ONG |
| 3301 | Organização Social (OS) | ONG |
| 3999 | Associação Privada | ONG |

O código 3999 inclui associações de assistência social e ONGs brasileiras segundo as notas explicativas da tabela. A seleção é intencionalmente conservadora: **3034** cartórios, **3085/3310** condomínios, **3107/3115** mediação e arbitragem, **3131** sindicatos, **3255–3298** estruturas partidárias, **3328** planos de benefícios e **3247** fundos privados não entram. **3077** serviço social autônomo e **3212** entidades domiciliadas no exterior também ficam de fora porque não representam, por si, uma ONG privada operacional neste cadastro. O CNAE alimentar ainda permite o perfil `empresa_alimentos` independentemente da natureza jurídica.

Se a fonte pública não trouxer um código de quatro dígitos, `sem_fins_lucrativos` fica falso. A API não infere elegibilidade só pela descrição. O script `scripts/atualizar_perfis.py` reconsulta contas antigas, mostra o plano sem alterar dados e só escreve no banco informado com `--aplicar`.

Fontes oficiais: [estrutura detalhada da TNJ 2021](https://concla.ibge.gov.br/images/concla/documentacao/CONCLA-TNJ2021-EstruturaDetalhada.pdf) e [notas explicativas](https://concla.ibge.gov.br/images/concla/documentacao/CONCLA-TNJ2021-NotasExplicativas.pdf).

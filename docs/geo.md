# Recomendação geográfica e rota de coleta

O PDF do projeto pede "Recomendação Geográfica" e "Otimização de rotas de coleta urbana". Esta parte cobre as duas, sem API paga e sem chave.

## Onde fica cada organização

`geo.py` transforma o endereço gravado no cadastro (`Logradouro, nº - Bairro, Município/UF - CEP`, montado pela consulta à Receita) em latitude e longitude. A ordem das fontes é esta:

| Ordem | Fonte | Precisão gravada | Quando |
|---|---|---|---|
| 1 | Cache na tabela `geolocalizacoes` | a que foi gravada | sempre que o endereço já foi resolvido |
| 2 | Sede do município em `data/municipios.csv` (5.571 municípios do IBGE com lat/lon) | `municipio` | na hora, offline, quando não há cache |
| 3 | [Nominatim](https://nominatim.org/) (OpenStreetMap), busca estruturada por rua, número, cidade e UF | `endereco` | em segundo plano |
| 4 | [BrasilAPI CEP v2](https://brasilapi.com.br/docs#tag/CEP-V2) | `cep` | em segundo plano, se o Nominatim não achar |

Regras de uso respeitoso das fontes gratuitas:

- **Nominatim**: no máximo 1 consulta por segundo (trava global de 1,1 s entre chamadas), `User-Agent` que identifica o projeto, cache permanente e nenhuma consulta em massa no caminho das requisições. Siga a [política de uso](https://operations.osmfoundation.org/policies/nominatim/).
- **BrasilAPI**: só para o CEP. Quando a coordenada do CEP cai a menos de 1 km da sede do município, ela é tratada como a própria sede (a BrasilAPI costuma devolver o centro da cidade) e fica a precisão `municipio`.
- Resultado a mais de 60 km da sede do município informado é descartado, para evitar uma rua homônima em outra cidade.
- Timeout de 3 s para conectar e 5 s para ler, sem seguir redirecionamentos.

**Nunca bloqueia.** Nenhuma rota espera a rede. Quem precisa de coordenada usa o cache ou a sede do município e pede o refinamento a uma fila em segundo plano: uma thread, no máximo 500 endereços na fila e sem repetir endereço. O cadastro e a edição de endereço disparam o refinamento **depois do commit**, por eventos do SQLAlchemy (`after_insert`/`after_update` em `Estabelecimento` mais `after_commit`), sem alterar `Cadastro.py`. Se a rede falhar, fica a sede do município e o cadastro segue igual.

Privacidade: a tabela guarda o **hash SHA-256** do endereço normalizado (não o texto) e a coordenada. As APIs públicas nunca devolvem coordenadas, só a distância em km arredondada. A rota, que tem coordenadas nos links do mapa, só é entregue à ONG que reservou, e o endereço de retirada ela já recebia na reserva.

`GEO_EXTERNO=0` desliga as consultas externas (só cache e sede do município). Os testes usam esse modo (`tests/conftest.py`).

### Contas existentes

```bash
python scripts/geocodificar.py              # quem ainda não tem coordenada (Nominatim → BrasilAPI → município)
python scripts/geocodificar.py --refinar    # tenta de novo quem ficou só na sede do município
python scripts/geocodificar.py --sem-rede   # só a sede do município, sem internet
```

O script lê `DATABASE_URL` como o app, respeita 1 consulta/s e só insere ou melhora linhas de `geolocalizacoes`. Ele nunca troca uma precisão melhor por uma pior.

## Distância na recomendação (`conexao.casar`)

A distância é a do círculo máximo (haversine, raio médio da Terra de 6.371 km), **em linha reta**. O caminho pelas ruas costuma ser maior.

| Distância até a ONG | Pontos |
|---|---|
| até 5 km | +15 |
| até 15 km | +12 |
| até 50 km | +9 |
| até 150 km | +5 |
| até 400 km | +2 |
| mais longe | 0 |

Quando há distância, ela **substitui** o antigo "+10 mesma UF" e vira um motivo legível: "a 3,8 km", "a cerca de 84 km" quando algum dos lados foi localizado só pela cidade, ou "na mesma cidade". Sem distância (endereço sem município reconhecível, ou pessoa física que não informou o CEP), vale a regra de UF de antes. A avaliação offline da recomendação (`scripts/avaliar_conexao.py`, 80 casos sem coordenadas) continua igual: top-1 0,8814, top-3 0,8814 e 100% de "sem sugestão" correta.

Origem da distância em `POST /reconecta/ia/sugerir-destino`:

- **Organização (CNPJ)**: o endereço do cadastro.
- **Pessoa física**: o campo opcional **"Seu CEP"** no assistente da Home. O CEP é localizado pela BrasilAPI (ou pela sede do município dele) e guardado em cache só pelo hash, sem ligação com quem consultou. A API também aceita `origem: {latitude, longitude}` no território brasileiro, usada só naquela consulta. O navegador não pede a localização do aparelho porque o site bloqueia geolocalização na `Permissions-Policy` (`geolocation=()`), decisão de segurança mantida.

## Avisos de excedente para as ONGs mais próximas

Quando uma empresa publica um excedente, `Excedentes._ongs_proximas` seleciona as ONGs com pedido aberto compatível (mesmo casamento da IA) que estejam **na mesma UF ou a até 50 km** (`RAIO_AVISO_KM`; vale também do outro lado da divisa). A lista é ordenada da mais próxima para a mais distante e limitada a 10 (`MAX_AVISOS`). Cada ONG recebe o aviso privado com a própria distância (`distancia_km`, `distancia`: "a 3,8 km"). O evento público continua sem distância.

## Rota de coleta: `GET /reconecta/excedentes/rota`

Só para ONG logada. Ela junta as reservas ainda no prazo, parte do endereço da ONG e volta para ele:

1. **Vizinho mais próximo**: sai da ONG e vai sempre para a retirada mais perto ainda não visitada.
2. **2-opt**: inverte trechos da ordem enquanto o percurso total (ida e volta) diminuir. Isso desfaz cruzamentos.

Com até 6 paradas, o resultado fica a no máximo 8% do ótimo da força bruta nos testes (`tests/test_geo.py`); em geral é o próprio ótimo. A resposta traz:

- a ordem, a distância de cada trecho e a acumulada, o endereço e o prazo de cada retirada;
- `link_osm` por trecho (OpenStreetMap, roteamento OSRM pelas ruas);
- `link_rota` com todas as paradas no mapa do [OSRM](https://map.project-osrm.org/), que usa dados do OpenStreetMap;
- `sem_localizacao` para retiradas cujo endereço não foi localizado;
- `aproximada: true` quando algum ponto foi localizado só pela cidade.

No painel, a seção **Minhas reservas de excedente** tem o botão **Rota de coleta**. Com a rota aberta, ela se refaz sozinha quando chega um evento de excedente (reserva, cancelamento ou retirada).

**Limites:** as distâncias são em linha reta, sem trânsito; a ordem não considera o prazo de cada retirada (o prazo aparece em cada parada para a ONG decidir); o OSRM público é um serviço de demonstração, sujeito a disponibilidade.

## Dados e licenças

- `data/municipios.csv`: derivado de [kelvins/municipios-brasileiros](https://github.com/kelvins/municipios-brasileiros) (MIT), que compila os municípios do IBGE com a coordenada da sede. A fonte, a transformação e a licença estão em `data/municipios-licenca.txt`.
- Nominatim e mapas: © colaboradores do OpenStreetMap, ODbL.
- BrasilAPI: serviço público e gratuito, sem chave.

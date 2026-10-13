"""Gera data/alimentos.csv a partir da lista curada abaixo.

Dataset sintético, escrito à mão para o ReConecta: nomes de alimentos do jeito que
uma empresa digitaria num pedido de doação. Não há dado coletado de usuários.

Uso:  python data/gerar_dataset.py
"""

import csv
import re
import unicodedata
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DESTINO = AQUI / "alimentos.csv"
COLUNAS = ["id", "texto", "categoria", "unidade_sugerida", "origem"]

# Cada linha: "unidade | nome base ; variação ; variação ..."
# A primeira grafia é o nome base; as demais são variações de escrita (plural,
# sem acento, abreviação) ou de embalagem (peso, volume, marca genérica).
CURADO = {
    "Hortifrúti": """
        kg | banana prata ; bananas ; banana nanica kg ; banana da terra
        kg | maçã ; maca fuji ; maçãs gala ; maca nacional cx 18kg
        kg | laranja pera ; laranjas ; laranja lima ; laranja p/ suco saco 20kg
        kg | tomate ; tomates maduros ; tomate italiano ; tomate cereja bandeja
        kg | batata inglesa ; batatas ; batata lavada saco 25kg ; batata doce
        kg | cebola ; cebolas ; cebola roxa ; cebola branca saco 20kg
        unidade | alface crespa ; alface americana ; pé de alface ; alface lisa un
        kg | cenoura ; cenouras ; cenoura kg ; cenoura ralada bandeja
        kg | abobrinha ; abobrinha italiana ; abobrinhas verdes
        kg | abóbora cabotiá ; abobora moranga ; abóbora japonesa kg
        kg | chuchu ; chuchus ; chuchu verde kg
        unidade | repolho verde ; repolho roxo ; repolho un ; repolhos
        unidade | couve manteiga ; maço de couve ; couve picada bandeja ; couve flor
        unidade | brócolis ; brocolis ninja ; brocolis maço
        kg | mamão formosa ; mamao papaia ; mamões
        kg | melancia ; melancias ; melancia fatiada ; melancia inteira kg
        kg | abacaxi pérola ; abacaxis ; abacaxi un
        kg | uva itália ; uvas sem semente ; uva rubi cx 500g
        kg | manga palmer ; mangas ; manga tommy kg
        kg | limão taiti ; limoes ; limão siciliano ; limao saco 5kg
        kg | pepino ; pepinos japoneses ; pepino caipira
        kg | pimentão verde ; pimentao vermelho ; pimentões coloridos
        kg | beterraba ; beterrabas ; beterraba kg
        kg | mandioca ; aipim descascado ; macaxeira kg ; mandioca congelada 1kg
        kg | alho ; alho nacional ; cabeça de alho ; alho descascado 500g
        unidade | cheiro verde ; salsinha maço ; cebolinha ; coentro maco
        kg | berinjela ; berinjelas ; beringela kg
        kg | quiabo ; quiabo bandeja 300g ; quiabos frescos
        kg | vagem ; vagem manteiga ; vagem kg
        unidade | milho verde espiga ; espigas de milho ; milho verde in natura
        kg | pera ; peras williams ; pera portuguesa
        kg | goiaba vermelha ; goiabas ; goiaba kg
        kg | abacate ; abacates ; avocado
        kg | morango ; morangos bandeja ; morango cx 250g
        kg | tangerina ponkan ; mexerica ; bergamota kg
        kg | inhame ; cará ; inhame kg
        unidade | rúcula ; rucula maço ; agrião ; espinafre maco
        kg | frutas variadas ; legumes sortidos ; verduras frescas ; caixa de hortaliças
        kg | melão amarelo ; melao ; melões
        kg | kiwi ; maracujá azedo ; maracuja kg ; coco verde
    """,
    "Padaria": """
        unidade | pão francês ; pao frances ; pães franceses ; paozinho ; pão de sal
        pacote | pão de forma ; pao de forma integral 500g ; pão de forma tradicional ; pao forma fatiado
        unidade | pão de hambúrguer ; pao de hamburguer pct 6 un ; pães de hambúrguer
        unidade | pão de hot dog ; pao de cachorro quente ; pão para hot dog pct
        unidade | pão doce ; pao doce com creme ; pães doces ; sonho de creme
        unidade | pão de queijo ; pao de queijo congelado 1kg ; pães de queijo ; paes de queijo coquetel
        unidade | pão integral ; pao integral ; pão de centeio ; pão multigrãos
        unidade | pão sírio ; pao sirio pct ; pão árabe ; pao pita
        unidade | pão de leite ; pao de leite pct ; bisnaguinha ; bisnaga
        unidade | baguete ; baguetes ; pão italiano ; pao ciabatta
        unidade | bolo de cenoura ; bolo de fubá ; bolo de chocolate ; bolos caseiros de padaria
        unidade | bolo simples ; bolo de laranja ; bolo formigueiro ; bolo inteiro 1kg
        pacote | biscoito cream cracker ; biscoito agua e sal 200g ; bolacha cream cracker ; biscoitos salgados
        pacote | biscoito maizena ; bolacha maisena ; biscoito maria pct ; bolachas doces
        pacote | biscoito recheado ; bolacha recheada chocolate ; biscoito recheado 130g ; bolachas recheadas
        pacote | biscoito de polvilho ; biscoito polvilho 100g ; rosquinha de polvilho ; sequilhos
        pacote | rosquinha de coco ; rosca doce ; rosquinhas ; rosca de leite
        pacote | torrada ; torradas integrais ; torrada tradicional 160g ; torradinhas
        unidade | croissant ; croissants ; croissant de manteiga
        unidade | broa de milho ; broas ; broinha de fubá
        unidade | pão de batata ; pao de batata recheado ; pães de batata
        unidade | cuca ; cuca de banana ; rocambole ; pão de mel
        pacote | pão bisnaguinha pct 300g ; pao bisnaguinha ; bisnaguinhas integrais
        unidade | pão de alho ; pao de alho pct ; pão de alho tradicional
        unidade | panetone ; panetones 400g ; chocotone ; colomba pascal
        unidade | muffin ; cupcake ; bolinho individual ; mini bolo
        pacote | wafer ; biscoito wafer morango ; bolacha wafer 140g
        unidade | pães variados ; paes do dia ; sobra de pães ; pão amanhecido
        pacote | biscoito integral ; cookies integrais ; cookie de aveia ; biscoito de leite
        unidade | massa de pizza ; disco de pizza pré-assado ; massa pronta de pastel ; massa folhada
    """,
    "Laticínios": """
        caixa | leite integral ; leite integral 1L ; leite longa vida ; leite uht cx 12
        caixa | leite desnatado ; leite desnatado 1 litro ; leite semidesnatado ; leite zero lactose
        pacote | leite em pó ; leite em po integral 400g ; leite em pó lata ; leite po instantaneo
        L | leite pasteurizado ; leite de saquinho ; leite tipo A ; leite fresco
        kg | queijo mussarela ; queijo muçarela fatiado ; mussarela kg ; mucarela peça
        kg | queijo prato ; queijo prato fatiado 150g ; queijo lanche
        kg | queijo minas frescal ; queijo minas ; queijo branco ; queijo frescal 500g
        kg | queijo coalho ; queijo coalho espeto ; queijo de coalho kg
        unidade | queijo parmesão ralado ; queijo ralado 50g ; parmesao ralado pct
        unidade | requeijão cremoso ; requeijao copo 200g ; requeijão ; requeijao culinario
        unidade | iogurte natural ; iogurte natural 170g ; iogurtes ; yogurt integral
        unidade | iogurte de morango ; iogurte sabor morango bandeja ; iogurte polpa ; iogurte liquido 900g
        unidade | iogurte grego ; iogurte grego 100g ; danone ; danoninho
        unidade | manteiga ; manteiga com sal 200g ; manteiga sem sal ; tablete de manteiga
        caixa | creme de leite ; creme de leite caixinha 200g ; creme de leite lata ; nata
        caixa | leite condensado ; leite condensado 395g ; leite condensado lata ; leite condensado cx
        unidade | bebida láctea ; bebida lactea morango ; bebida láctea 1L ; bebida lactea fermentada
        unidade | ricota ; ricota fresca ; queijo ricota 400g
        unidade | cream cheese ; cream cheese 150g ; queijo cremoso
        unidade | coalhada ; coalhada seca ; coalhada integral
        unidade | doce de leite ; doce de leite pastoso 400g ; doce de leite pote
        unidade | leite fermentado ; leite fermentado 80g ; yakult ; lactobacilos
        kg | queijo provolone ; provolone ; queijo gouda ; queijo cheddar fatiado
        unidade | petit suisse ; queijinho petit suisse ; petit suisse morango
        unidade | chantilly ; creme chantilly spray ; creme de leite fresco
        kg | laticínios variados ; laticinios ; derivados de leite ; produtos lácteos
        caixa | leite achocolatado ; leite com chocolate cx 200ml ; leite sabor chocolate
        unidade | queijo cottage ; cottage 200g ; queijo quark
        L | leite de cabra ; leite de cabra 1L ; leite cru resfriado
        unidade | kefir ; kefir de leite ; iogurte kefir
    """,
    "Carnes e peixes": """
        kg | carne moída ; carne moida de primeira ; carne moída kg ; patinho moido
        kg | carne bovina ; carne de boi ; carne de segunda ; acém em cubos
        kg | alcatra ; coxão mole ; coxao duro ; contra filé
        kg | músculo bovino ; musculo ; costela bovina ; carne para ensopado
        kg | frango inteiro ; frango congelado ; frangos ; frango resfriado kg
        kg | peito de frango ; filé de peito de frango ; file de frango 1kg ; peito de frango sem osso
        kg | coxa e sobrecoxa ; coxa de frango ; sobrecoxa kg ; coxinha da asa
        kg | carne suína ; carne de porco ; lombo suíno ; pernil suino
        kg | bisteca suína ; bisteca de porco ; costelinha suína
        kg | linguiça toscana ; linguica calabresa ; linguiça de frango ; linguicas
        kg | salsicha ; salsicha hot dog 3kg ; salsichas ; salsicha de frango
        kg | presunto ; presunto fatiado ; presunto cozido 200g ; apresuntado
        kg | mortadela ; mortadela fatiada ; mortadela defumada kg
        kg | bacon ; bacon em cubos ; bacon fatiado 250g ; toucinho
        kg | peixe ; peixes ; filé de peixe ; file de pescada
        kg | tilápia ; filé de tilapia ; tilapia congelada 800g
        kg | sardinha fresca ; sardinhas ; sardinha kg
        unidade | sardinha em lata ; sardinha lata 125g ; sardinha em óleo ; lata de sardinha
        unidade | atum em lata ; atum ralado 170g ; atum sólido ; lata de atum
        unidade | ovos ; ovo ; dúzia de ovos ; ovos brancos cartela 30
        unidade | ovos caipiras ; ovos vermelhos ; bandeja de ovos ; ovo de codorna
        kg | fígado bovino ; figado ; moela de frango ; coração de frango
        kg | hambúrguer bovino ; hamburguer congelado cx ; hambúrgueres ; hamburguer de frango
        kg | almôndega ; almondegas congeladas ; almôndegas de carne
        kg | carne seca ; charque ; carne de sol ; jabá
        kg | camarão ; camarao limpo ; camarão congelado 400g
        kg | salmão ; file de salmao ; merluza ; cação em postas
        kg | peito de peru ; blanquet de peru ; peito de peru fatiado
        kg | nuggets de frango ; empanado de frango 300g ; steak de frango ; frango empanado
        kg | carnes variadas ; cortes de frango ; proteína animal ; cortes bovinos
    """,
    "Grãos e cereais": """
        kg | arroz ; arroz tipo 1 5kg ; arroz branco ; arroz agulhinha ; pacote de arroz 5 kg
        kg | arroz integral ; arroz integral 1kg ; arroz parboilizado ; arroz parbo 5kg
        kg | feijão carioca ; feijao carioca 1kg ; feijão ; feijao tipo 1
        kg | feijão preto ; feijao preto 1kg ; feijões ; feijão fradinho
        kg | feijão branco ; feijao de corda ; feijão vermelho ; feijao jalo
        kg | lentilha ; lentilha 500g ; lentilhas
        kg | grão de bico ; grao de bico 500g ; grão-de-bico
        kg | ervilha seca ; ervilha partida 500g ; ervilhas secas
        pacote | macarrão espaguete ; macarrao espaguete 500g ; macarrão ; espaguete n 8
        pacote | macarrão parafuso ; macarrao parafuso 500g ; macarrão penne ; massa fusilli
        pacote | macarrão instantâneo ; miojo ; macarrao instantaneo 80g ; lamen
        kg | farinha de trigo ; farinha de trigo 1kg ; farinha trigo tipo 1 ; trigo
        kg | farinha de mandioca ; farinha de mandioca torrada ; farinha mandioca 500g ; farinha d'água
        kg | fubá ; fuba mimoso 1kg ; fubá de milho ; farinha de milho
        kg | flocão de milho ; flocao 500g ; cuscuz de milho ; farinha de milho flocada
        kg | aveia em flocos ; aveia flocos finos 200g ; aveia ; farelo de aveia
        pacote | granola ; granola tradicional 1kg ; cereal matinal ; sucrilhos
        kg | milho de pipoca ; milho pipoca 500g ; milho para pipoca
        kg | canjica ; canjica branca 500g ; canjiquinha ; milho para canjica
        kg | quinoa ; quinoa em grãos ; chia ; linhaça
        kg | trigo para quibe ; trigo quibe 500g ; triguilho
        kg | soja em grãos ; proteína de soja ; proteina texturizada de soja 400g ; carne de soja
        kg | polvilho doce ; polvilho azedo 500g ; goma de tapioca ; tapioca
        pacote | massa para lasanha ; massa de lasanha 500g ; macarrão talharim ; massa com ovos
        kg | amendoim ; amendoim cru 500g ; castanha de caju ; castanha do pará
        kg | farinha de rosca ; farinha de rosca 500g ; farinha panko
        kg | grãos variados ; graos ; cereais ; cesta de grãos
        kg | arroz e feijão ; arroz com feijao kit ; kit arroz feijão macarrão
        kg | sagu ; sagu de mandioca 500g ; cevadinha
        kg | farinha de arroz ; farinha de aveia ; farinha integral 1kg
    """,
    "Refeições prontas": """
        unidade | marmita ; marmitas ; marmitex ; marmita fitness congelada
        unidade | quentinha ; quentinhas ; quentinha de arroz feijão e frango ; quentinha média
        unidade | refeição pronta ; refeicoes prontas ; refeição congelada ; prato pronto
        unidade | prato feito ; PF ; prato executivo ; prato do dia
        L | sopa ; sopa de legumes ; sopão ; sopa pronta 500ml
        L | caldo verde ; caldo de feijão ; caldo de mandioca pronto ; canja de galinha
        unidade | lasanha ; lasanha congelada 600g ; lasanha bolonhesa ; lasanhas prontas
        unidade | pizza ; pizzas ; pizza congelada ; pizza de mussarela
        unidade | sanduíche ; sanduiche natural ; sanduíches ; lanche natural
        unidade | lanche ; kit lanche ; lanches prontos ; x-salada
        unidade | coxinha ; coxinhas ; salgado frito ; salgados de festa
        unidade | esfiha ; esfihas de carne ; esfirra ; empada de frango
        unidade | pastel ; pasteis de carne ; pastel assado ; pastelzinho
        unidade | torta de frango ; torta salgada ; empadão ; tortas salgadas fatia
        kg | feijoada ; feijoada pronta ; feijão tropeiro pronto ; baião de dois
        kg | strogonoff de frango ; estrogonofe ; strogonoff pronto
        kg | arroz cozido ; arroz pronto ; arroz temperado cozido ; risoto
        kg | macarronada ; macarrão ao molho pronto ; yakisoba ; espaguete à bolonhesa pronto
        kg | escondidinho ; escondidinho de carne seca ; purê de batata pronto
        unidade | hot dog ; cachorro quente pronto ; cachorros quentes
        unidade | hambúrguer montado ; x-burguer ; lanche de hambúrguer
        kg | frango assado ; frango de padaria assado ; galeto assado
        kg | salada pronta ; salada de maionese ; salpicão ; salada de frutas pote
        unidade | cuscuz paulista ; quiche ; panqueca recheada
        unidade | comida pronta ; sobra limpa do almoço ; refeição do buffet ; comida do restaurante
        unidade | kit refeição ; kit almoço ; refeição individual embalada
        kg | carne cozida com legumes ; picadinho pronto ; ensopado pronto
        unidade | tapioca recheada ; crepe ; wrap de frango
        unidade | marmita vegetariana ; marmita vegana ; refeicao vegetariana
        kg | polenta pronta ; angu ; nhoque ao sugo pronto
    """,
    "Bebidas não alcoólicas": """
        L | água mineral ; agua mineral 500ml ; água sem gás ; galão de água 20L ; agua
        L | água com gás ; agua com gas 1,5L ; água gaseificada
        L | suco de laranja ; suco de laranja integral 1L ; suco natural ; sucos
        L | suco de uva ; suco de uva integral ; suco uva 1,5L
        caixa | suco de caixinha ; suco caixinha 200ml ; néctar de pêssego ; nectar de manga 1L
        pacote | suco em pó ; refresco em po ; suco tang ; refresco sabor laranja
        L | refrigerante ; refrigerantes ; refrigerante 2L ; refri guaraná
        L | refrigerante de cola ; coca ; guaraná lata 350ml ; refrigerante laranja pet 2 litros
        L | água de coco ; agua de coco 1L ; água de coco caixinha
        L | chá gelado ; cha mate pronto ; chá mate 1,5L ; chá de limão gelado
        caixa | chá em sachê ; cha de camomila cx ; chá de erva doce ; sachês de chá
        L | isotônico ; isotonico 500ml ; bebida isotônica
        L | bebida de soja ; leite de soja ; suco de soja 1L ; bebida vegetal de aveia
        L | suco concentrado ; suco de caju concentrado 500ml ; suco de maracujá concentrado
        L | polpa de fruta ; polpa de acerola 1kg ; polpas congeladas ; polpa de maracuja
        L | limonada ; limonada pronta ; laranjada
        L | energético sem álcool ; energetico lata ; bebida energética
        L | água saborizada ; agua saborizada limão ; água aromatizada
        L | chá verde ; cha preto ; chá de hibisco ; chá mate a granel
        L | bebidas ; bebidas nao alcoolicas ; bebidas variadas ; fardo de bebidas
        L | xarope de groselha ; groselha ; xarope de guaraná
        L | garrafa de água ; agua mineral fardo 12 un ; copo de água 200ml ; agua galao
        L | suco de maçã ; suco de abacaxi ; suco de goiaba 1L ; suco de manga
        L | suco verde ; suco detox ; suco de couve com limão
        L | refrigerante zero ; refri sem açúcar ; guaraná zero 2L
        L | bebida láctea de soja ; bebida de amêndoas ; leite de aveia ; leite vegetal
        L | mate ; mate leão ; erva mate para chimarrão ; tereré
        L | café pronto ; café coado ; garrafa de café
        L | vitamina de frutas ; smoothie ; batida de frutas sem álcool
        L | caldo de cana ; garapa ; água tônica
    """,
    "Outros": """
        kg | açúcar ; acucar refinado 1kg ; açúcar cristal 5kg ; acucar mascavo
        kg | sal ; sal refinado 1kg ; sal grosso ; sal iodado
        L | óleo de soja ; oleo de soja 900ml ; óleo ; oleo de girassol
        L | azeite ; azeite de oliva 500ml ; azeite extra virgem
        pacote | café em pó ; cafe 500g ; café torrado e moído ; cafe soluvel
        unidade | molho de tomate ; molho de tomate sachê 340g ; extrato de tomate ; polpa de tomate
        unidade | milho verde em lata ; milho em conserva 200g ; lata de milho ; milho verde lata
        unidade | ervilha em lata ; ervilha em conserva ; seleta de legumes lata
        unidade | maionese ; maionese 500g ; ketchup ; mostarda
        L | vinagre ; vinagre de álcool 750ml ; vinagre de maçã
        unidade | margarina ; margarina 500g ; margarina com sal ; creme vegetal
        pacote | achocolatado em pó ; achocolatado 400g ; chocolate em pó ; cacau em pó
        unidade | gelatina ; gelatina em pó morango ; gelatinas ; pudim em pó
        unidade | mel ; mel de abelha 300g ; melado de cana
        unidade | geleia ; geleia de morango ; goiabada ; marmelada
        unidade | chocolate ; barra de chocolate 90g ; bombom ; chocolates
        pacote | tempero pronto ; tempero completo ; colorau ; orégano
        pacote | caldo de galinha em cubo ; caldo de carne tablete ; caldo knorr
        pacote | fermento em pó ; fermento biológico seco ; fermento quimico 100g
        pacote | amido de milho ; maisena 500g ; amido
        unidade | leite de coco ; leite de coco 200ml ; coco ralado ; coco ralado 100g
        unidade | azeitona ; azeitonas verdes ; palmito ; champignon em conserva
        pacote | batata palha ; batata palha 500g ; salgadinho de milho ; pipoca de micro-ondas
        pacote | paçoca ; pé de moleque ; doce de amendoim ; rapadura
        pacote | bala ; balas sortidas ; pirulito ; chiclete
        unidade | papinha de bebê ; papinha infantil ; fórmula infantil ; mingau infantil
        unidade | adoçante ; adocante liquido ; stevia
        unidade | molho shoyu ; molho de soja ; molho inglês ; molho de pimenta
        unidade | cesta básica ; cestas basicas ; kit alimentação ; alimentos não perecíveis
        unidade | creme de avelã ; pasta de amendoim ; doce de banana ; cocada
        unidade | suplemento alimentar ; whey protein ; barra de cereal ; barrinha de cereais
        unidade | sorvete ; picolé ; açaí congelado ; sobremesa gelada
        pacote | pimenta do reino ; canela em pó ; cominho ; louro
        unidade | produtos diversos ; itens diversos ; mantimentos ; alimentos diversos
    """,
}


def normalizar(texto):
    """Chave de comparação: minúsculas, sem acento e com espaços simples."""
    sem = "".join(c for c in unicodedata.normalize("NFKD", texto.lower())
                  if not unicodedata.combining(c))
    return " ".join(sem.split())


def linhas():
    vistos = set()
    saida = []
    for categoria, bloco in CURADO.items():
        for bruta in bloco.strip().splitlines():
            unidade, _, grafias = bruta.partition("|")
            unidade = unidade.strip()
            for posicao, grafia in enumerate(g.strip() for g in grafias.split(";")):
                chave = normalizar(grafia)
                if not grafia or chave in vistos:
                    continue  # sem duplicata, nem só por acento ou caixa
                vistos.add(chave)
                if posicao == 0:
                    origem = "nome_base"
                elif re.search(r"\d", grafia):
                    origem = "embalagem"
                else:
                    origem = "variacao_escrita"
                saida.append([len(saida) + 1, grafia, categoria, unidade, origem])
    return saida


def main():
    dados = linhas()
    with DESTINO.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo, lineterminator="\n")
        escritor.writerow(COLUNAS)
        escritor.writerows(dados)
    por_categoria = {}
    for linha in dados:
        por_categoria[linha[2]] = por_categoria.get(linha[2], 0) + 1
    print(f"{len(dados)} linhas em {DESTINO.name}")
    for categoria, total in por_categoria.items():
        print(f"  {categoria}: {total}")


if __name__ == "__main__":
    main()

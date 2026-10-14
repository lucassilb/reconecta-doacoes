"""Rota de coleta da ONG: ordena as retiradas dos excedentes reservados.

Partida e chegada no endereço da ONG; ordem pelo vizinho mais próximo seguido de 2-opt
(`geo.ordenar_rota`); distâncias em linha reta (haversine). Os links abrem o
OpenStreetMap, que traça o caminho pelas ruas, sem chave nem serviço pago.
"""

from flask_restx import Namespace, Resource, fields
from sqlalchemy.orm import selectinload

import geo
from Auth import usuario_atual
from Excedentes import status_efetivo
from fuso import agora_brasilia_sem_fuso, iso_prazo
from models import Excedente

ns = Namespace("rota", description="Rota de coleta dos excedentes reservados pela ONG")

parada_model = ns.model("ParadaRota", {
    "ordem": fields.Integer, "excedente_id": fields.Integer, "empresa": fields.String,
    "endereco": fields.String, "retirar_ate": fields.String,
    "distancia_km": fields.Float(description="Do ponto anterior, em linha reta"),
    "acumulado_km": fields.Float, "precisao": fields.String, "link_osm": fields.String,
})
rota_model = ns.model("RotaColeta", {
    "partida": fields.Raw, "paradas": fields.List(fields.Nested(parada_model)),
    "sem_localizacao": fields.List(fields.Raw), "retorno_km": fields.Float,
    "total_km": fields.Float, "link_rota": fields.String, "metodo": fields.String,
    "aproximada": fields.Boolean,
})


def _arredondar(km):
    return round(km, 1)


@ns.route("")
class RotaColeta(Resource):
    @ns.response(200, "Ordem de retirada, distâncias e links do OpenStreetMap", rota_model)
    @ns.response(401, "Sem sessão")
    @ns.response(403, "Apenas ONGs")
    def get(self):
        """Ordena as retiradas pendentes da ONG logada (reservas ainda no prazo)."""
        atual = usuario_atual()
        if not atual:
            return {"codigo": "NAO_AUTENTICADO", "mensagem": "Entre para continuar."}, 401
        tipo, ong = atual
        if tipo != "empresa" or not ong.sem_fins_lucrativos:
            return {"codigo": "APENAS_ONGS", "mensagem": "A rota de coleta é para ONGs."}, 403
        reservas = (Excedente.query.options(selectinload(Excedente.publicador),
                                             selectinload(Excedente.itens))
                    .filter(Excedente.reservado_por_id == ong.id,
                            Excedente.status == "RESERVADO",
                            Excedente.retirar_ate > agora_brasilia_sem_fuso())
                    .order_by(Excedente.retirar_ate, Excedente.id).all())
        reservas = [r for r in reservas if status_efetivo(r) == "RESERVADO"]
        partida = geo.localizar(ong.endereco)
        if partida is None:
            return {"codigo": "SEM_LOCALIZACAO",
                    "mensagem": "Não conseguimos localizar o endereço da sua organização."}, 422
        com_ponto, sem_ponto = [], []
        for reserva in reservas:
            ponto = geo.localizar(reserva.publicador.endereco)
            (com_ponto if ponto is not None else sem_ponto).append((reserva, ponto))
        ordem = geo.ordenar_rota(partida, [ponto for _, ponto in com_ponto])
        paradas, anterior, acumulado = [], partida, 0.0
        for posicao, indice in enumerate(ordem, 1):
            reserva, ponto = com_ponto[indice]
            trecho = geo.haversine_km(anterior, ponto)
            acumulado += trecho
            paradas.append({
                "ordem": posicao, "excedente_id": reserva.id,
                "empresa": reserva.publicador.nome,
                "endereco": reserva.publicador.endereco,
                "retirar_ate": iso_prazo(reserva.retirar_ate),
                "itens": [item.nome for item in reserva.itens],
                "distancia_km": _arredondar(trecho), "acumulado_km": _arredondar(acumulado),
                "precisao": ponto.precisao, "link_osm": geo.link_osm((anterior, ponto)),
            })
            anterior = ponto
        retorno = geo.haversine_km(anterior, partida) if paradas else 0.0
        trajeto = [partida, *(com_ponto[i][1] for i in ordem), partida] if paradas else []
        return {
            "partida": {"nome": ong.nome, "precisao": partida.precisao},
            "paradas": paradas,
            "sem_localizacao": [{"excedente_id": r.id, "empresa": r.publicador.nome,
                                 "endereco": r.publicador.endereco} for r, _ in sem_ponto],
            "retorno_km": _arredondar(retorno),
            "total_km": _arredondar(acumulado + retorno),
            "link_rota": geo.link_rota_completa(trajeto) if paradas else None,
            "metodo": "vizinho mais próximo + 2-opt; distâncias em linha reta",
            "aproximada": any(p["precisao"] == "municipio" for p in paradas) or
                          partida.precisao == "municipio",
        }, 200

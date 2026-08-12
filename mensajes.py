import cv2
import numpy as np
from ultralytics import YOLO
import requests
import time
import constants
import asyncio
from spade_bdi.bdi import BDIAgent
from spade.behaviour import CyclicBehaviour
import json
from spade.message import Message


class FipaReceiver(CyclicBehaviour):
    async def run(self):
        # Espera recibir mensajes wait to receive messages
        msg = await self.receive(timeout=2.0)
        if msg:
            # SPADE extrae los metadatos FIPA automaticamente y los pone en un diccionario
            performative = msg.metadata.get("performative")
            Content = msg.body
            ont = msg.metadata.get("ontology")
            print(ont)
            print(msg)

            print(f"[{self.agent.jid}] FIPA message received:")
            print(f" - Performative: {performative}")
            print(f" - Content: {Content}")
            
            # Razonamiento basado en el estándar FIPA
            if performative == "request":
                # Si Java hace una petición (REQUEST), inyectamos una orden al motor BDI
                self.agent.bdi.set_belief(f'java_command("{Content}")')
                print("hola")
                
            elif performative == "inform":
                # Si Java solo te informa de un estado (INFORM)
                self.agent.bdi.set_belief(f'java_notification("{Content}")')
                print('vemos')
                
            elif performative == "query-ref":
                # Si Java te pregunta algo
                pass
        else:
            print('no')


class BDI_agent_monitor(BDIAgent):
    """
    Initialize agents with the model to monitor on the cameras
    Args:
        BDIAgent (_type_): let us use BDI agents
    """
    def __init__(self, jid, passw, behaviour):
        super().__init__(jid, passw, behaviour, verify_security=False)  # this is the agent

    async def setup(self):
        print(f"Starting {self.jid} agent...")
        self.add_behaviour(FipaReceiver())


async def main():

    monitor1 = BDI_agent_monitor(f"monitor1@{constants.IP_SERVER}", constants.PASS_XMPP, "ejemplo.asl")

    # NUEVO 1: Le decimos a la librería base (slixmpp) que es seguro usar texto plano en esta LAN
    # monitor1.client.plugin['feature_mechanisms'].unencrypted_plain = True

    # NUEVO 2: Agregamos auto_register=True para crear la cuenta si no existe en el servidor
    # await monitor1.start(auto_register=True)
    await monitor1.start()

    try:
        while True:
            await asyncio.sleep(2)
    except KeyboardInterrupt:
        print("WARNING. Couldn't connect to cameras")
        await monitor1.stop()


if __name__ == "__main__":
    asyncio.run(main())

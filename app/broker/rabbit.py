from faststream.rabbit import RabbitBroker, RabbitExchange, RabbitQueue
from faststream.rabbit.schemas import ExchangeType


class RabbitSettings:
    exchange_name = "payments.domain"
    main_queue = "payments.created"
    dlq_queue = "payments.errors"
    routing_key = "event.payment_created"
    dlq_routing_key = "event.payment_rejected"


domain_exchange = RabbitExchange(
    name=RabbitSettings.exchange_name,
    type=ExchangeType.TOPIC,
    durable=True,
)

created_queue = RabbitQueue(
    name=RabbitSettings.main_queue,
    durable=True,
    routing_key=RabbitSettings.routing_key,
    arguments={
        "x-dead-letter-exchange": RabbitSettings.exchange_name,
        "x-dead-letter-routing-key": RabbitSettings.dlq_routing_key,
    },
)

error_queue = RabbitQueue(
    name=RabbitSettings.dlq_queue,
    durable=True,
    routing_key=RabbitSettings.dlq_routing_key,
)


def create_rabbit_broker(url: str) -> RabbitBroker:
    broker = RabbitBroker(url)
    return broker

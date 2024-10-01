import os
import pytest
from swarmauri.llms.concrete.AI21StudioModel import AI21StudioModel as LLM
from swarmauri.conversations.concrete.Conversation import Conversation

from swarmauri.messages.concrete.HumanMessage import HumanMessage
from swarmauri.messages.concrete.SystemMessage import SystemMessage
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("AI21STUDIO_API_KEY")


@pytest.fixture(scope="module")
def ai21studio_model():
    if not API_KEY:
        pytest.skip("Skipping due to environment variable not set")
    llm = LLM(api_key=API_KEY)
    return llm


def get_allowed_models():
    if not API_KEY:
        return []
    llm = LLM(api_key=API_KEY)
    return llm.allowed_models


@pytest.mark.unit
def test_ubc_resource(ai21studio_model):
    assert ai21studio_model.resource == "LLM"


@pytest.mark.unit
def test_ubc_type(ai21studio_model):
    assert ai21studio_model.type == "AI21StudioModel"


@pytest.mark.unit
def test_serialization(ai21studio_model):
    assert (
        ai21studio_model.id
        == LLM.model_validate_json(ai21studio_model.model_dump_json()).id
    )


@pytest.mark.unit
def test_default_name(ai21studio_model):
    assert ai21studio_model.name == "jamba-1.5-mini"


@pytest.mark.unit
@pytest.mark.parametrize("model_name", get_allowed_models())
def test_no_system_context(ai21studio_model, model_name):
    model = ai21studio_model
    model.name = model_name
    conversation = Conversation()

    input_data = "Hello"
    human_message = HumanMessage(content=input_data)
    conversation.add_message(human_message)

    model.predict(conversation=conversation)
    prediction = conversation.get_last().content
    assert isinstance(prediction, str)


@pytest.mark.unit
@pytest.mark.parametrize("model_name", get_allowed_models())
def test_preamble_system_context(ai21studio_model, model_name):
    model = ai21studio_model
    model.name = model_name

    conversation = Conversation()

    system_context = 'You only respond with the following phrase, "Jeff"'
    human_message = SystemMessage(content=system_context)
    conversation.add_message(human_message)

    input_data = "Hi"
    human_message = HumanMessage(content=input_data)
    conversation.add_message(human_message)

    model.predict(conversation=conversation)
    prediction = conversation.get_last().content
    assert type(prediction) == str
    assert "Jeff" in prediction, f"Test failed for model: {model_name}"

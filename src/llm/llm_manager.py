import os
from typing import Any, List, Union
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from loguru import logger

load_dotenv()


class AIAdapter:
    """
    Adapter to interact directly with Google Gemini LLM via langchain-google-genai.
    """
    def __init__(self, config: dict = None, api_key: str = None):
        from config import GEMINI_API_KEY, GEMINI_MODEL_NAME

        # Resolve Gemini API Key: check GEMINI_API_KEY env, passed api_key, or config
        resolved_key = (
            GEMINI_API_KEY
            or os.getenv("GEMINI_API_KEY")
            or (api_key if api_key and not api_key.startswith("sk-") else None)
            or api_key
            or os.getenv("GOOGLE_API_KEY")
        )

        model_name = GEMINI_MODEL_NAME or os.getenv("GEMINI_MODEL_NAME", "gemini-flash-latest")

        if not resolved_key:
            raise ValueError(
                "Gemini API key not found. Please set GEMINI_API_KEY in your .env file "
                "or provide it in data_folder/secrets.yaml."
            )

        logger.info(f"Initializing AIAdapter with ChatGoogleGenerativeAI using model: {model_name}")
        self.model = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=resolved_key,
            temperature=0.4,
        )
        logger.info("ChatGoogleGenerativeAI model initialized successfully.")

    def invoke(self, prompt: Union[str, List[BaseMessage]]) -> BaseMessage:
        """Invokes the Gemini model."""
        logger.debug(f"Invoking Gemini model with prompt type: {type(prompt)}")
        try:
            response = self.model.invoke(prompt)
            logger.debug("Received response from Gemini model.")
            return response
        except Exception as e:
            logger.error(f"Error invoking Gemini model: {e}")
            raise


class TensorZeroChatModelWrapper:
    """
    Wrapper around the Chat model to ensure clean invocation and output types.
    Maintained for backward compatibility with existing AiAnswerer chains.
    """
    def __init__(self, llm: Any):
        self.llm = llm
        logger.debug(f"ChatModelWrapper initialized with LLM: {llm}")

    def __call__(self, messages: Union[List[BaseMessage], Any]) -> BaseMessage:
        """Invokes the underlying chat model."""
        logger.debug(f"Wrapper invoking LLM with messages: {messages}")
        try:
            reply = self.llm.invoke(messages)

            # Ensure return type is AIMessage
            if not isinstance(reply, AIMessage):
                logger.warning(f"Unexpected reply type from LLM: {type(reply)}. Expected AIMessage.")
                if isinstance(reply, str):
                    return AIMessage(content=reply)
                elif hasattr(reply, "content"):
                    return AIMessage(content=str(reply.content))
                else:
                    raise TypeError(f"Cannot handle LLM reply type: {type(reply)}")

            return reply

        except Exception as e:
            logger.error(f"Error during LLM invocation within wrapper: {str(e)}")
            raise


# Alias for general usage
ChatModelWrapper = TensorZeroChatModelWrapper


import os
import json
import logging
from typing import List, Dict, Literal, Optional, Any, Union

from openai import OpenAI
import google.generativeai as genai

logger = logging.getLogger(__name__)

class ChatCompletionError(Exception):
	"""Custom exception for chat completion errors."""
	pass

class ChatCompletionClient:
	"""Unified client for chat completion (OpenAI-compatible, or Gemini)."""

	def __init__(
			self,
			provider_configs_list: List[Dict[str, Any]]
	):
		"""
		Initializes client with provider configurations.
		Args:
		   provider_configs_list: List of provider config dicts.
		"""
		if not provider_configs_list:
			raise ValueError("Provider configs list cannot be empty.")

		# Create internal dict keyed by 'cmd'
		self.provider_configs_by_cmd: Dict[str, Dict[str, Any]] = {
			p['cmd']: p for p in provider_configs_list if 'cmd' in p
		}
		if not self.provider_configs_by_cmd:
			raise ValueError("No valid provider configurations found with 'cmd' keys.")

		self.openai_clients: Dict[str, OpenAI] = {}
		self.gemini_native_clients: Dict[str, genai.GenerativeModel] = {}

		self._initialize_clients()

	def _initialize_clients(self):
		"""Initializes API clients."""
		for cmd, config in self.provider_configs_by_cmd.items():
			identifier = cmd
			display_name = config.get("name", cmd)

			is_gemini = config.get("is_gemini", False)
			api_key = config.get("api_key")
			model = config.get("model")
			base_url = config.get("base_url")

			if not api_key:
				logger.warning(f"API key missing for '{display_name}' (cmd: '{identifier}'). Skipping.")
				continue
			if not model:
				logger.warning(f"Default model missing for '{display_name}' (cmd: '{identifier}'). Skipping.")
				continue

			try:
				if is_gemini:
					genai.configure(api_key=api_key)
					self.gemini_native_clients[identifier] = genai.GenerativeModel(model_name=model)
					logger.info(f"Gemini client '{display_name}' (cmd: '{identifier}') initialized.")
				else:
					if not base_url:
						logger.warning(f"Base URL missing for OpenAI-compatible client '{display_name}' (cmd: '{identifier}'). Skipping.")
						continue

					client_kwargs = {"api_key": api_key, "base_url": base_url}
					self.openai_clients[identifier] = OpenAI(**client_kwargs)
					logger.info(f"OpenAI-compatible client '{display_name}' (cmd: '{identifier}') initialized.")
			except Exception as e:
				logger.error(f"Error initializing client '{display_name}' (cmd: '{identifier}'): {e}")

	def _get_openai_client(self, provider_cmd: str) -> OpenAI:
		"""Retrieves an initialized OpenAI-compatible client."""
		client = self.openai_clients.get(provider_cmd)
		if not client:
			raise ChatCompletionError(
				f"OpenAI-compatible client '{provider_cmd}' not initialized. Check config."
			)
		return client

	def chat_completion(self,
						provider_config: Dict[str, Any],
						messages: List[Dict[str, str]],
						system_prompt: Optional[str] = None,
						temperature: float = 0.7,
						max_tokens: Optional[int] = None,
						**kwargs) -> str:
		"""
		Performs a chat completion request.
		Args:
		   provider_config: Config dict for the LLM provider.
		   messages: List of message dicts.
		   system_prompt: Optional system behavior/context.
		   temperature: Controls randomness.
		   max_tokens: Max tokens to generate.
		   **kwargs: Additional API arguments.
		Returns:
		   Content of the generated message.
		Raises:
		   ChatCompletionError: If client not initialized or API call fails.
		   ValueError: If provider config invalid.
		"""
		provider_cmd = provider_config.get("cmd")
		if not provider_cmd:
			raise ValueError("Provider config missing 'cmd' field.")

		display_name = provider_config.get("name", provider_cmd)

		is_gemini = provider_config.get("is_gemini", False)
		model = provider_config.get("model")

		if not model:
			raise ChatCompletionError(f"No model found in config for provider '{display_name}' (cmd: '{provider_cmd}').")

		if not is_gemini: # OpenAI-compatible
			openai_client = self._get_openai_client(provider_cmd)

			openai_messages = []
			if system_prompt:
				openai_messages.append({"role": "system", "content": system_prompt})
			openai_messages.extend(messages)

			try:
				response = openai_client.chat.completions.create(
					model=model,
					messages=openai_messages,
					temperature=temperature,
					max_tokens=max_tokens,
					stream=False,
					**kwargs
				)
				return response.choices[0].message.content
			except Exception as e:
				raise ChatCompletionError(f"OpenAI-compatible chat completion for '{display_name}' (cmd: '{provider_cmd}') failed: {e}")

		else: # Gemini
			if provider_cmd not in self.gemini_native_clients:
				raise ChatCompletionError(
					f"Gemini client '{display_name}' (cmd: '{provider_cmd}') not initialized. Check 'api_key'."
				)

			gemini_model_instance = self.gemini_native_clients[provider_cmd]

			gemini_messages = []
			if system_prompt:
				gemini_messages.append({'role': 'user', 'parts': [system_prompt]})

			for msg in messages:
				role = 'user' if msg['role'] == 'user' else 'model'
				gemini_messages.append({'role': role, 'parts': [msg['content']]})

			try:
				response = gemini_model_instance.generate_content(
					contents=gemini_messages,
					generation_config=genai.types.GenerationConfig(
						temperature=temperature,
						max_output_tokens=max_tokens
					),
					stream=False,
					**kwargs
				)
				if response.candidates:
					return response.candidates[0].content.parts[0].text
				else:
					logger.warning(f"Gemini response for '{display_name}' (cmd: '{provider_cmd}') had no candidates. Possibly blocked or empty response.")
					return ""
			except Exception as e:
				raise ChatCompletionError(f"Gemini chat completion for '{display_name}' (cmd: '{provider_cmd}') failed: {e}")

#!/usr/bin/env python3
# edit config vars in .env
import os, logging, json, functools, time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from inc.chat_completion import ChatCompletionClient

# Enable logging
logging.basicConfig(
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
	level=logging.INFO
)
logger = logging.getLogger(__name__)

# Change current working directory to script directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Load config
try:
	with open('./config.json', 'r') as f:
		config = json.loads(f.read())
except Exception as e:
	logger.critical('Error loading config.json: %s', e)
	quit()

# Initialize ChatCompletionClient
try:
	client = ChatCompletionClient(config['chat_providers'])
except Exception as e:
	logger.critical('Error initializing ChatCompletionClient: %s', e)
	quit()


# Helper function to check chat ID authorization
def is_chat_authorized(update: Update) -> bool:
	# Check 'enforce_chat_ids' as per the latest config.json
	if config['misc_options'].get('enforce_chat_ids', False):
		allowed_chat_ids = config['misc_options'].get('allow_chat_ids', [])
		if allowed_chat_ids: # Only enforce if the list is not empty
			chat_id = update.effective_chat.id
			if chat_id not in allowed_chat_ids:
				logger.info(f"Ignoring unauthorized chat ID: {chat_id}")
				return False
	return True


# Define command handlers
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Sends a message with available commands."""
	logger.info('help_command() update: %s', update)

	if not is_chat_authorized(update):
		return # Silently ignore unauthorized chat

	help_text = "Available commands:\n`/help`\n"

	# /id command is hidden and should not be listed in /help
	# help_text += "`/id`\n" # Removed as per user request

	for provider_config in config['chat_providers']:
		# Ensure memory_wipe_subcmd exists before adding to help text
		wipe_subcmd_display = ""
		if config['chat_options'].get('memory_enabled', False) and config['chat_options'].get('memory_wipe_subcmd'):
			wipe_subcmd_display = f" [{config['chat_options']['memory_wipe_subcmd']}]"
		help_text += f"`/{provider_config['cmd']}{wipe_subcmd_display} [text]`\n"

	if update.effective_message:
		await update.effective_message.reply_text(help_text, parse_mode='markdown')


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE, provider_config: dict) -> None:
	"""Handles chat commands for different providers."""
	if not is_chat_authorized(update):
		return # Silently ignore unauthorized chat

	display_name = provider_config.get('name', provider_config['cmd'])
	provider_cmd = provider_config['cmd'] # Memory key

	# Get message object (new or edited)
	message_to_process = update.edited_message if update.edited_message else update.message

	if not message_to_process:
		logger.warning("Chat update without effective message.")
		return # Cannot reply

	chat_id = message_to_process.chat_id
	user_message_id = message_to_process.message_id # User's message ID

	# Initialize bot_replies in chat_data
	if 'bot_replies' not in context.chat_data:
		context.chat_data['bot_replies'] = {}

	# Get ID of bot's previous reply
	bot_reply_id_for_edit = context.chat_data['bot_replies'].get(user_message_id)

	try:
		# Send "Please wait..." for EDITED messages only
		if update.edited_message and bot_reply_id_for_edit:
			try:
				await context.bot.edit_message_text(
					chat_id=chat_id,
					message_id=bot_reply_id_for_edit,
					text="Please wait...",
					parse_mode=None
				)
				logger.info('Edited previous bot response to "Please wait..." for user message ID %s', user_message_id)
			except Exception as edit_e:
				logger.warning('Failed to edit message %s to "Please wait..." (error: %s). Proceeding without update.', bot_reply_id_for_edit, edit_e)

		# Handle empty arguments or determine user query
		if not context.args:
			response_content = (
				f"Please provide a message after the /{provider_cmd} command. "
				f"E.g., /{provider_cmd} What is the capital of France?"
			)
			parse_mode_for_response = None

			# Attempt to edit "Please wait..." with usage or send new
			if bot_reply_id_for_edit:
				try:
					await context.bot.edit_message_text(
						chat_id=chat_id,
						message_id=bot_reply_id_for_edit,
						text=response_content,
						parse_mode=parse_mode_for_response
					)
				except Exception as edit_e:
					logger.warning('Failed to edit message %s with usage text (error: %s). Sending new usage message.', bot_reply_id_for_edit, edit_e)
					await message_to_process.reply_text(response_content, parse_mode=parse_mode_for_response)
			else:
				new_reply = await message_to_process.reply_text(response_content, parse_mode=parse_mode_for_response)
				context.chat_data['bot_replies'][user_message_id] = new_reply.message_id
			return

		user_query = " ".join(context.args)
		logger.info('Incoming query for %s (cmd: %s): %s', display_name, provider_cmd, user_query)

		# Handle memory wipe subcommand
		memory_wipe_subcmd = config['chat_options'].get('memory_wipe_subcmd')
		if memory_wipe_subcmd and user_query.strip().lower().startswith(memory_wipe_subcmd.lower()):
			if config['chat_options'].get('memory_enabled', False):
				chat_memories = context.chat_data.setdefault('chat_memories', {})
				if provider_cmd in chat_memories:
					wiped_count = len(chat_memories[provider_cmd])
					chat_memories[provider_cmd].clear() # Wipe memory for this provider
					logger.info('Memory for provider %s wiped. %d pairs removed.', provider_cmd, wiped_count)

				response_content = "Memory erased."
			else:
				response_content = "Memory is not enabled."

			# Send/Edit "Memory erased." message
			if bot_reply_id_for_edit:
				try:
					await context.bot.edit_message_text(
						chat_id=chat_id,
						message_id=bot_reply_id_for_edit,
						text=response_content,
						parse_mode=None
					)
				except Exception as edit_e:
					logger.warning('Failed to edit message %s with "Memory erased." (error: %s). Sending new message.', bot_reply_id_for_edit, edit_e)
					await message_to_process.reply_text(response_content, parse_mode=None)
			else:
				new_reply = await message_to_process.reply_text(response_content, parse_mode=None)
				context.chat_data['bot_replies'][user_message_id] = new_reply.message_id
			return # Exit after handling memory wipe

		# Prepare messages for LLM, including memory if enabled
		messages_for_llm = []
		chat_completion_system_prompt = None

		if config['chat_options'].get('memory_enabled', False):
			chat_memories = context.chat_data.setdefault('chat_memories', {})
			provider_memory = chat_memories.setdefault(provider_cmd, [])

			current_time = time.time()
			memory_expires = config['chat_options'].get('memory_expires', 0)
			memory_max_pairs = config['chat_options'].get('memory_max_pairs', 0)

			if config["chat_options"].get("system_prompt"):
				messages_for_llm.append({"role": "system", "content": config["chat_options"]["system_prompt"]})

			# Clean up expired messages (by time)
			if memory_expires > 0:
				initial_memory_count = len(provider_memory)
				provider_memory[:] = [
					entry for entry in provider_memory if (current_time - entry['timestamp']) < memory_expires
				]
				removed_count_expires = initial_memory_count - len(provider_memory)
				if removed_count_expires > 0:
					logger.debug('Removed %d expired memory pairs for %s. Remaining: %d.', removed_count_expires, provider_cmd, len(provider_memory))

			# Handle Edited Message Memory Update
			if update.edited_message:
				initial_user_message_id = update.edited_message.message_id
				initial_memory_count = len(provider_memory)
				provider_memory[:] = [
					entry for entry in provider_memory if entry.get('user_message_id') != initial_user_message_id
				]
				removed_count_edited = initial_memory_count - len(provider_memory)
				if removed_count_edited > 0:
					logger.debug('Removed %d old memory pair(s) for edited message ID %s. Remaining: %d.', removed_count_edited, initial_user_message_id, len(provider_memory))

			# Enforce max_pairs limit (by count)
			if memory_max_pairs > 0:
				removed_count_max_pairs = 0
				while len(provider_memory) > memory_max_pairs:
					provider_memory.pop(0)
					removed_count_max_pairs += 1
				if removed_count_max_pairs > 0:
					logger.debug('Removed %d memory pairs due to max_pairs limit for %s. Remaining: %d.', removed_count_max_pairs, provider_cmd, len(provider_memory))

			for entry in provider_memory:
				messages_for_llm.extend(entry['messages'])

			messages_for_llm.append({"role": "user", "content": user_query})

			r = client.chat_completion(
				provider_config,
				messages_for_llm,
				temperature=config["chat_options"]["temperature"]
			)

			# Store new memory entry
			new_memory_entry = {
				'timestamp': time.time(),
				'user_message_id': user_message_id,
				'messages': [{"role": "user", "content": user_query}, {"role": "assistant", "content": r}]
			}
			provider_memory.append(new_memory_entry)
			logger.debug('Added new memory entry for %s. Total entries: %d.', provider_cmd, len(provider_memory))

		else: # Memory is not enabled
			messages_for_llm.append({"role": "user", "content": user_query})
			chat_completion_system_prompt = config["chat_options"].get("system_prompt")

			r = client.chat_completion(
				provider_config,
				messages_for_llm,
				system_prompt=chat_completion_system_prompt,
				temperature=config["chat_options"]["temperature"]
			)

		# Removed chat response prefix as per user request
		final_response_text = r
		parse_mode_for_response = 'markdown'

		# Send/Edit final response
		if bot_reply_id_for_edit:
			try:
				await context.bot.edit_message_text(
					chat_id=chat_id,
					message_id=bot_reply_id_for_edit,
					text=final_response_text,
					parse_mode=parse_mode_for_response
				)
				logger.info('Edited bot response for user message ID %s with final content.', user_message_id)
			except Exception as edit_e:
				logger.warning('Failed to edit message %s with final response (error: %s). Sending new final response.', bot_reply_id_for_edit, edit_e)
				new_reply = await message_to_process.reply_text(final_response_text, parse_mode=parse_mode_for_response)
				context.chat_data['bot_replies'][user_message_id] = new_reply.message_id
		else:
			new_reply = await message_to_process.reply_text(final_response_text, parse_mode=parse_mode_for_response)
			context.chat_data['bot_replies'][user_message_id] = new_reply.message_id

		logger.info('chat() response from %s (cmd: %s): %s', display_name, provider_cmd, r)

	except Exception as e:
		error_message = f"An error occurred while chatting with {display_name}: {e}"
		if bot_reply_id_for_edit:
			try:
				await context.bot.edit_message_text(
					chat_id=chat_id,
					message_id=bot_reply_id_for_edit,
					text=error_message,
					parse_mode=None
				)
				logger.error('Edited bot response to error for user message ID %s: %s', user_message_id, e)
			except Exception as edit_e:
				logger.error('Failed to edit message %s with error (error: %s). Sending new error message.', bot_reply_id_for_edit, edit_e)
				await message_to_process.reply_text(error_message, parse_mode=None)
		else:
			await message_to_process.reply_text(error_message, parse_mode=None)
		logger.error('chat() error with provider %s (cmd: %s): %s', display_name, provider_cmd, e)


async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Sends information about the current chat."""
	logger.info('id_command() update: %s', update)
	chat_info = update.effective_chat

	if not update.effective_message:
		logger.warning("id update without effective message.")
		return

	# Check for authorization
	if not is_chat_authorized(update):
		return # Silently ignore unauthorized chat

	# Output for /id uses markdown as per user request
	if chat_info.type in ['group', 'supergroup']:
		await update.effective_message.reply_text(
			f"This is a group chat. Chat ID: `{chat_info.id}`\n"
			f"Chat Title: `{chat_info.title}`",
			parse_mode='markdown' # Retained markdown for /id command
		)
	else:
		await update.effective_message.reply_text(
			f"Chat ID: `{chat_info.id}`\n",
			parse_mode='markdown' # Retained markdown for /id command
		)


def main() -> None:
	"""Starts the bot."""
	application = Application.builder().token(config['misc_options']['bot_token']).build()

	# Register command handlers
	application.add_handler(CommandHandler("help", help_command))

	# /id command is always registered (not disabled by config)
	application.add_handler(CommandHandler("id", id_command))

	# Add all providers
	for provider_config in config['chat_providers']:
		command_name = provider_config["cmd"]
		handler_callback = functools.partial(chat, provider_config=provider_config)
		application.add_handler(CommandHandler(command_name, handler_callback))

	# Unused: Register message handler for non-command text
	# application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

	logger.info("Bot started. Press Ctrl-C to stop.")
	application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
	main()

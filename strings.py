"""All user-facing text for JUGNU, in one place.

To add a language:
  1. Add a new dictionary to STRINGS with exactly the same keys as "en".
  2. Add its code to LANGUAGES (the Language button cycles through that list).

Keep placeholders such as {error} and {when} identical in every language.
Never name a placeholder "language" or "key": those are get_string() arguments.
Brand text (the name JUGNU and its acronym expansion) is not translated.
"""

DEFAULT_LANGUAGE = "en"
LANGUAGES = ["en", "hinglish"]

STRINGS = {
    "en": {
        "language_name": "English",
        "language_btn": "🌐  Language: {name}",
        # Sidebar and header
        "new_chat_btn": "＋  New Chat",
        "history_label": "CHAT HISTORY",
        "clear_chat_btn": "▤  Clear Current Chat",
        "voice_on": "🔊  Voice: On",
        "voice_off": "🔇  Voice: Off",
        "voice_settings_btn": "🎚  Voice Settings",
        "voice_settings_title": "Voice Settings",
        "voice_rate_label": "Speed: {value} words/min",
        "voice_volume_label": "Volume: {value}%",
        "voice_choice_label": "Voice",
        "voice_default_name": "System default",
        "voice_test_btn": "▶  Test voice",
        "voice_test_sample": "Hello! This is how I sound.",
        "voice_close_btn": "Close",
        "theme_to_light": "☼  Light Mode",
        "theme_to_dark": "☾  Dark Mode",
        "header_title": "✦  Your little genius is here!",
        # Chat area
        "send_btn": "➤  Send",
        "stop_btn": "⏹  Stop",
        "you_label": "You",
        "welcome_title": "Hey! I'm JUGNU",
        "welcome_prompt": "What would you like to explore today?",
        # Status line
        "status_ready": "Ready",
        "status_offline": "Ollama offline",
        "status_thinking": "Thinking…",
        "status_streaming": "Generating…",
        "status_save_error": "Could not save history: {error}",
        # Dialogs
        "clear_dialog_title": "Clear Current Chat",
        "clear_dialog_message": "Permanently remove this chat from your history?",
        "chat_menu_rename": "✎  Rename",
        "chat_menu_delete": "🗑  Delete",
        "rename_dialog_title": "Rename Chat",
        "rename_dialog_prompt": "New name for this chat:",
        "rename_save_btn": "Save",
        "rename_cancel_btn": "Cancel",
        "delete_chat_title": "Delete Chat",
        "delete_chat_message": "Permanently delete “{title}”? This cannot be undone.",
        "code_copy_btn": "⧉ Copy code",
        "code_copied_btn": "✓ Copied!",
        # Search and Export
        "search_placeholder": "🔍 Search chats... (Ctrl+F)",
        "search_matches_count": "{count} found",
        "search_no_matches": "No matches found",
        "chat_menu_export": "⤓  Export Chat…",
        "export_dialog_title": "Export Chat Transcript",
        "export_success_title": "Export Successful",
        "export_success_msg": "Chat successfully exported to {path}",
        "export_error_msg": "Could not export chat: {error}",
        # Personas
        "sidebar_personas": "🎭  Personas",
        "persona_label": "Persona:",
        "persona_manage_title": "Manage Personas",
        "persona_new_btn": "+ New Persona",
        "persona_save_btn": "Save Persona",
        "persona_delete_btn": "Delete",
        "persona_name_label": "Name:",
        "persona_desc_label": "Description:",
        "persona_temp_label": "Creativity (Temperature: {temp}):",
        "persona_prompt_label": "System Instructions:",
        "persona_delete_confirm": "Delete persona “{name}”? This cannot be undone.",
        "persona_builtin_badge": "Built-in",
        "persona_custom_badge": "Custom",
        # Automation & Scheduler
        "auto_btn": "⏱  Tasks",
        "auto_dialog_title": "Automation Studio",
        "auto_task_label": "Scheduled Tasks",
        "auto_task_new": "+ New Task",
        "auto_task_run": "Run Now",
        "auto_task_pause": "Pause Scheduler",
        "auto_task_resume": "Resume Scheduler",
        "auto_notify_success": "Task “{name}” completed successfully.",
        "auto_notify_error": "Task “{name}” failed: {error}",
        # Agent & Sandboxed Tools
        "tool_card_title": "Tool Execution",
        "tool_status_success": "Success",
        "tool_status_error": "Error",
        "tool_btn_details": "Details",
        # Command Palette and Shortcuts
        "command_palette_btn": "⌘  Command Palette (Ctrl+K)",
        "command_palette_title": "Command Palette",
        "command_palette_placeholder": "> Type a command or search actions... (Esc to close)",
        "command_palette_no_matches": "No matching commands found",
        "command_palette_footer": "↑ / ↓ to navigate  •  Enter to run  •  Esc to close",
        "shortcuts_help_title": "Keyboard Shortcuts",
        "cmd_new_chat": "New Conversation",
        "cmd_clear_chat": "Clear Current Conversation",
        "cmd_toggle_theme": "Toggle Dark / Light Theme",
        "cmd_toggle_language": "Switch Language (English / Hinglish)",
        "cmd_toggle_voice": "Toggle Voice Output (Mute / Unmute)",
        "cmd_voice_settings": "Open Voice Settings",
        "cmd_prev_chat": "Previous Conversation",
        "cmd_next_chat": "Next Conversation",
        "cmd_shortcuts_help": "Keyboard Shortcuts Cheat Sheet",
        "cmd_quit": "Quit Application",
        "cat_chat": "Chat",
        "cat_appearance": "Appearance",
        "cat_voice": "Voice",
        "cat_settings": "Settings",
        "cat_navigation": "Navigation",
        "cat_help": "Help",
        "cat_app": "Application",
        # Document Attachment and Ingestion
        "attach_file_btn": "📎 Attach",
        "attach_dialog_title": "Select Document or Code File",
        "attach_error_title": "Attachment Error",
        "attach_err_binary": "Cannot attach binary file: {filename}",
        "attach_err_large": "File too large: {filename} ({size}). Limit is 512 KB.",
        "attach_err_read": "Could not read file: {error}",
        # Model switcher and pull manager
        "model_btn": "🧠 {name}",
        "model_menu_title": "Local Models",
        "model_menu_refresh": "🔄  Refresh Models",
        "model_menu_pull": "⬇  Download New Model…",
        "model_status_switching": "Switching model to {name}…",
        "model_pull_title": "Download Ollama Model",
        "model_pull_prompt": "Choose a recommended model or type any model name:",
        "model_pull_recommended": "Recommended Models:",
        "model_pull_custom_label": "Model name:",
        "model_pull_start_btn": "Download Model",
        "model_pull_cancel_btn": "Cancel",
        "model_pull_close_btn": "Close",
        "model_pull_status_idle": "Enter model name and click Download.",
        "model_pull_status_downloading": "Downloading {model}… {percent}% ({mb})",
        "model_pull_status_verifying": "Verifying {model}…",
        "model_pull_status_success": "✓ Successfully downloaded {model}!",
        "model_pull_status_error": "Download failed: {error}",
        "model_pull_empty_name": "Please enter a model name.",
        "model_no_models_found": "No local models found",
        # Replies shown when something goes wrong
        "error_empty_reply": "Sorry, I got an empty response. Please try again.",
        "error_invalid_response": "Ollama returned an invalid response. Please try again.",
        "error_timeout": ("The reply is taking too long. Please check that Ollama is running "
                          "and the model has loaded, then try again."),
        "error_connection": ("Can't connect to Ollama. Please check that Ollama is running "
                             "and the model is installed."),
        "error_generic": "Error: {error}",
        # Answered locally, without calling the model
        "time_answer": "The current local date and time is: {when}",
        # Added to the system prompt so the model replies in this language
        "prompt_language_rule": ("Always answer in clear and simple English only. "
                                 "Never answer in Hindi or Hinglish. "),
    },
    "hinglish": {
        "language_name": "Hinglish",
        "language_btn": "🌐  Bhasha: {name}",
        # Sidebar and header
        "new_chat_btn": "＋  Nayi Chat",
        "history_label": "PURANI CHATS",
        "clear_chat_btn": "▤  Current Chat Clear Karo",
        "voice_on": "🔊  Voice: Chalu",
        "voice_off": "🔇  Voice: Band",
        "voice_settings_btn": "🎚  Voice Settings",
        "voice_settings_title": "Voice Settings",
        "voice_rate_label": "Bolne ki speed: {value} words/min",
        "voice_volume_label": "Awaaz: {value}%",
        "voice_choice_label": "Voice",
        "voice_default_name": "System default",
        "voice_test_btn": "▶  Voice test karo",
        "voice_test_sample": "Hello! Main aise bolta hoon.",
        "voice_close_btn": "Band karo",
        "theme_to_light": "☼  Light Mode",
        "theme_to_dark": "☾  Dark Mode",
        "header_title": "✦  Aapka chhota genius aa gaya!",
        # Chat area
        "send_btn": "➤  Bhejo",
        "stop_btn": "⏹  Roko",
        "you_label": "Aap",
        "welcome_title": "Hey! Main JUGNU hoon",
        "welcome_prompt": "Aaj aap kya explore karna chahenge?",
        # Status line
        "status_ready": "Taiyaar",
        "status_offline": "Ollama offline hai",
        "status_thinking": "Soch raha hoon…",
        "status_streaming": "Likh raha hoon…",
        "status_save_error": "History save nahi ho payi: {error}",
        # Dialogs
        "clear_dialog_title": "Current Chat Clear Karo",
        "clear_dialog_message": "Is current chat ko history se permanently clear kar dein?",
        "chat_menu_rename": "✎  Naam Badlo",
        "chat_menu_delete": "🗑  Delete Karo",
        "rename_dialog_title": "Chat ka Naam Badlo",
        "rename_dialog_prompt": "Is chat ka naya naam:",
        "rename_save_btn": "Save Karo",
        "rename_cancel_btn": "Cancel",
        "delete_chat_title": "Chat Delete Karo",
        "delete_chat_message": "“{title}” ko permanently delete kar dein? Ye wapas nahi aayegi.",
        "code_copy_btn": "⧉ Code copy karo",
        "code_copied_btn": "✓ Copy ho gaya!",
        # Search and Export
        "search_placeholder": "🔍 Chats dhoondein... (Ctrl+F)",
        "search_matches_count": "{count} mile",
        "search_no_matches": "Koi match nahi mila",
        "chat_menu_export": "⤓  Chat Export Karo…",
        "export_dialog_title": "Chat Export Karein",
        "export_success_title": "Export Ho Gaya",
        "export_success_msg": "Chat safaltapoorvak {path} par export ho gayi",
        "export_error_msg": "Chat export nahi ho saki: {error}",
        # Personas
        "sidebar_personas": "🎭  Personas",
        "persona_label": "Persona:",
        "persona_manage_title": "Personas Manage Karein",
        "persona_new_btn": "+ Naya Persona",
        "persona_save_btn": "Save Persona",
        "persona_delete_btn": "Delete",
        "persona_name_label": "Naam:",
        "persona_desc_label": "Description:",
        "persona_temp_label": "Creativity (Temperature: {temp}):",
        "persona_prompt_label": "System Instructions:",
        "persona_delete_confirm": "Kya aap “{name}” ko delete karna chahte hain?",
        "persona_builtin_badge": "Built-in",
        "persona_custom_badge": "Custom",
        # Automation & Scheduler
        "auto_btn": "⏱  Tasks",
        "auto_dialog_title": "Automation Studio",
        "auto_task_label": "Scheduled Tasks",
        "auto_task_new": "+ Naya Task",
        "auto_task_run": "Abhi Chalao",
        "auto_task_pause": "Scheduler Roko",
        "auto_task_resume": "Scheduler Shuru Karo",
        "auto_notify_success": "Task “{name}” safaltapoorvak pura ho gaya.",
        "auto_notify_error": "Task “{name}” fail ho gaya: {error}",
        # Agent & Sandboxed Tools
        "tool_card_title": "Tool Chalaya Gaya",
        "tool_status_success": "Safal",
        "tool_status_error": "Truti",
        "tool_btn_details": "Jankari",
        # Command Palette and Shortcuts
        "command_palette_btn": "⌘  Command Palette (Ctrl+K)",
        "command_palette_title": "Command Palette",
        "command_palette_placeholder": "> Command likhein ya action dhoondein... (Esc se band karein)",
        "command_palette_no_matches": "Koi matching command nahi mila",
        "command_palette_footer": "↑ / ↓ se navigate karein  •  Enter se chalayein  •  Esc se band karein",
        "shortcuts_help_title": "Keyboard Shortcuts",
        "cmd_new_chat": "Nayi Conversation Shuru Karein",
        "cmd_clear_chat": "Maujooda Conversation Saaf Karein",
        "cmd_toggle_theme": "Theme Badlein (Dark / Light)",
        "cmd_toggle_language": "Bhasha Badlein (English / Hinglish)",
        "cmd_toggle_voice": "Awaaz On / Off Karein (Mute / Unmute)",
        "cmd_voice_settings": "Voice Settings Kholein",
        "cmd_prev_chat": "Pichli Conversation Par Jayein",
        "cmd_next_chat": "Agli Conversation Par Jayein",
        "cmd_shortcuts_help": "Keyboard Shortcuts Cheat Sheet",
        "cmd_quit": "JUGNU Band Karein",
        "cat_chat": "Chat",
        "cat_appearance": "Appearance",
        "cat_voice": "Awaaz",
        "cat_settings": "Settings",
        "cat_navigation": "Navigation",
        "cat_help": "Madad",
        "cat_app": "Application",
        # Document Attachment and Ingestion
        "attach_file_btn": "📎 Jodein",
        "attach_dialog_title": "Document ya Code File Chunein",
        "attach_error_title": "Attachment Error",
        "attach_err_binary": "Binary file attach nahi kar sakte: {filename}",
        "attach_err_large": "File bahut badi hai: {filename} ({size}). Limit 512 KB hai.",
        "attach_err_read": "File read nahi ho saki: {error}",
        # Model switcher and pull manager
        "model_btn": "🧠 {name}",
        "model_menu_title": "Local Models",
        "model_menu_refresh": "🔄  Models Refresh Karo",
        "model_menu_pull": "⬇  Naya Model Download Karo…",
        "model_status_switching": "Model {name} par switch kar rahe hain…",
        "model_pull_title": "Ollama Model Download Karo",
        "model_pull_prompt": "Recommended model chunein ya koi bhi naam type karein:",
        "model_pull_recommended": "Recommended Models:",
        "model_pull_custom_label": "Model ka naam:",
        "model_pull_start_btn": "Download Karo",
        "model_pull_cancel_btn": "Cancel",
        "model_pull_close_btn": "Band Karo",
        "model_pull_status_idle": "Model ka naam daalein aur Download par click karein.",
        "model_pull_status_downloading": "{model} download ho raha hai… {percent}% ({mb})",
        "model_pull_status_verifying": "{model} verify ho raha hai…",
        "model_pull_status_success": "✓ {model} successfully download ho gaya!",
        "model_pull_status_error": "Download fail ho gaya: {error}",
        "model_pull_empty_name": "Kripya model ka naam daalein.",
        "model_no_models_found": "Koi local model nahi mila",
        # Replies shown when something goes wrong
        "error_empty_reply": "Sorry, mujhe empty response mila. Ek baar phir try karo.",
        "error_invalid_response": "Ollama se sahi jawab nahi mila. Ek baar phir try karo.",
        "error_timeout": ("Response mein zyada time lag raha hai. "
                          "Ollama/model load check karke dobara try karo."),
        "error_connection": ("Ollama se connect nahi ho pa raha. "
                             "Check karo ki Ollama running hai aur model installed hai."),
        "error_generic": "Error: {error}",
        # Answered locally, without calling the model
        "time_answer": "Abhi local date aur time hai: {when}",
        # Added to the system prompt so the model replies in this language
        "prompt_language_rule": ("Always answer in Hinglish: Hindi written in the English (Roman) "
                                 "alphabet, mixed naturally with common English words, the way "
                                 "people chat in India. Never use Devanagari script. "),
    },
}

SYSTEM_PROMPT_INTRO = (
    "You are JUGNU, a helpful, friendly personal AI assistant. "
    "Give clear, concise answers by default (usually 2-5 sentences). "
    "Use easy language. If more detail is needed, provide it. "
)
SYSTEM_PROMPT_CLOCK = (
    "Current local date and time: {now}. "
    "For date/time questions, use this exact current context; never guess."
)


def normalize_language(value):
    """Return `value` if it is a known language code, otherwise the default."""
    if isinstance(value, str) and value in STRINGS:
        return value
    return DEFAULT_LANGUAGE


def next_language(current):
    """The language after `current` in LANGUAGES, wrapping around."""
    current = normalize_language(current)
    return LANGUAGES[(LANGUAGES.index(current) + 1) % len(LANGUAGES)]


def get_string(language, key, **kwargs):
    """Look up `key` in `language`, filling in {placeholders} from kwargs.

    A key missing from the chosen language falls back to English, and a key
    missing everywhere returns the key itself, so the UI never crashes on text.
    """
    text = STRINGS[normalize_language(language)].get(key)
    if text is None:
        text = STRINGS[DEFAULT_LANGUAGE].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def build_system_prompt(language, now_text, persona=None):
    """System prompt for the model: persona, reply-language rule, and the clock."""
    if persona and hasattr(persona, "system_prompt") and persona.system_prompt:
        intro = persona.system_prompt.strip() + " "
    else:
        intro = SYSTEM_PROMPT_INTRO
    return (intro
            + get_string(language, "prompt_language_rule")
            + SYSTEM_PROMPT_CLOCK.format(now=now_text))

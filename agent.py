import os
import base64
import datetime
import io
import extract_msg

from google.adk.agents import Agent, SequentialAgent # Added SequentialAgent
from google.adk.tools.tool_context import ToolContext
from typing import Optional, Dict, Any

# --- Environment Variable Setup ---
# This should ideally be done outside the script or loaded from a .env file for better practice
# For example, using a library like python-dotenv
#os.environ["GOOGLE_API_KEY"] = "AIzaSyBNIK9PQuqDovP5b3gRugzgDTlxEvI2KMA" # IMPORTANT: Replace with your actual key or load securely
#os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"

# --- Tool Definition (Used by the InitialEmailParserAgent) ---
def parse_email_tool(
    tool_context: Optional[ToolContext], # ToolContext can be optional if not always provided by ADK runtime for all tool calls
    email_file_path: Optional[str] = None,
    email_file_bytes_b64: Optional[str] = None
) -> Dict[str, Any]:
    """
    Parses an email file's content (from path or base64 encoded bytes)
    to extract subject, body, sender, etc.
    """
    email_file_bytes = None
    if email_file_bytes_b64:
        try:
            email_file_bytes = base64.b64decode(email_file_bytes_b64)
        except Exception as e:
            return {"status": "error", "message": f"Failed to decode base64 content: {str(e)}"}

    if not email_file_bytes and not email_file_path:
        return {"status": "error", "message": "No email file path or base64 content provided."}

    try:
        if email_file_bytes:
            msg_file = io.BytesIO(email_file_bytes)
            msg = extract_msg.Message(msg_file)
        elif email_file_path:
            msg = extract_msg.Message(email_file_path)
        else:
            return {"status": "error", "message": "No valid email input provided to parse."}

        email_date_to_serialize = None
        if msg.date:
            if isinstance(msg.date, datetime.datetime):
                email_date_to_serialize = msg.date.isoformat()
            else:
                email_date_to_serialize = str(msg.date)

        attachments_list = []
        if msg.attachments:
            for att in msg.attachments:
                if hasattr(att, 'longFilename') and att.longFilename:
                    attachments_list.append(str(att.longFilename))

        parsed_dict = {
            "status": "success",
            "subject": str(msg.subject) if msg.subject else None,
            "body": str(msg.body) if msg.body else None,
            "sender": str(msg.sender) if msg.sender else None,
            "to": str(msg.to) if msg.to else None,
            "date": email_date_to_serialize,
            "attachments": attachments_list
        }
        return parsed_dict

    except Exception as e:
        return {"status": "error", "message": f"Failed to parse email: {str(e)}"}

# --- Import Existing Sub-Agents ---
# These paths assume this file is in the same directory as the 'sub_agents' folder
# or that the Python path is set up accordingly.
# If this code is inside 'email_manager_agent/agent.py', the leading dot is correct.
# If this is a new pipeline file at the root, imports might need adjustment.
# For this example, I'll assume the imports are correct as you provided them relative to this file.

from .sub_agents.email_classifier_agent.agent import email_classifier_agent
from .sub_agents.email_summarizer_agent.agent import email_summarizer_agent
from .sub_agents.invoice_extractor_agent.agent import invoice_extractor_agent
from .sub_agents.invoice_database_agent.agent import invoice_database_agent
from .sub_agents.auto_responce_agent.agent import auto_response_agent # Corrected typo if it was 'auto_responce_agent'

# --- Define the New Initial Parsing Agent ---
initial_email_parser_agent = Agent(
    name="InitialEmailParserAgent",
    model="gemini-2.0-flash-001", # Or your preferred model
    description="Parses the initial email file (from path or base64 bytes) and populates the state.",
    instruction="""
    You will receive an initial input which may contain 'email_file_path' or 'email_file_bytes_b64'.
    Your primary task is to use the `parse_email_tool` with the provided input to parse the email.

    After parsing, if successful, you MUST store the following extracted information into the shared state:
    - 'email_subject': The subject of the email.
    - 'email_body': The main content/body of the email.
    - 'sender_email': The sender's email address (from 'sender' field of parsed data).
    - 'recipient_email': The recipient's email address (from 'to' field of parsed data).
    - 'email_date': The date of the email (as an ISO formatted string).
    - 'email_attachments': A list of attachment filenames.

    If parsing fails, store the 'status' and 'message' from the tool's error response into the state
    under keys like 'parsing_status' and 'parsing_message', and then stop processing.
    Ensure the state keys are exactly as specified for successful parsing to allow subsequent agents to use them.
    For example, the state after your operation should look like:
    {
        "email_subject": "...",
        "email_body": "...",
        "sender_email": "...",
        "recipient_email": "...",
        "email_date": "...",
        "email_attachments": [...]
    }
    """,
    tools=[parse_email_tool]
)

# --- Define the Sequential Email Processing Pipeline ---
# This replaces your previous 'email_manager_agent = Agent(...)'
email_processing_pipeline = SequentialAgent(
    name="EmailProcessingPipeline",
    description="A sequential pipeline that parses, classifies, summarizes, extracts invoice details, queries a database, and generates an auto-response for emails.",
    sub_agents=[
        initial_email_parser_agent,    # Step 0: Parse the email
        email_classifier_agent,        # Step 1: Classify
        email_summarizer_agent,        # Step 2: Summarize
        invoice_extractor_agent,       # Step 3: Extract Invoice Number (conditional logic within this agent)
        invoice_database_agent,        # Step 4: Get Invoice Details (conditional logic within this agent)
        auto_response_agent            # Step 5: Generate Auto-Response
    ]
    # Note: A SequentialAgent typically doesn't have its own 'model', 'instruction', or 'tools'
    # in the same way a regular Agent does. Its main role is to orchestrate the sequence.
    # The individual sub_agents will use their own models, instructions, and tools.
)

# To make this usable, you might want to assign it to a common name if other scripts expect 'root_agent'
root_agent = email_processing_pipeline

# You would then use 'root_agent' (or 'email_processing_pipeline') with your ADK runtime.
# For example:
# adk_runtime.register_agent(root_agent)
# adk_runtime.interact(agent_name="EmailProcessingPipeline", initial_input={"email_file_path": "path/to/your/email.msg"})
# or
# adk_runtime.interact(agent_name="EmailProcessingPipeline", initial_input={"email_file_bytes_b64": "base64_encoded_string_of_email"})
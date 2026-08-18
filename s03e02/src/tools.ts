import { apiPost, getApiKey, submit } from "../../api";
import { setTimeout } from 'node:timers/promises';
import {
    ALLOWED_COMMANDS,
    CommandResponse,
    FORBIDDEN_DIRECTORIES,
    learnCommandsFromHelp,
    sanitizeEditlineCommand,
    trackGitignoredPaths,
    validateCommand,
    warnOnReboot,
} from "./shell-guardrails";

export interface ToolDefinition {
    type: 'function'
    function: {
        name: string
        description: string
        parameters: Record<string, unknown>
    }
}

export interface Tool {
    definition: ToolDefinition
    handler: (arg: any) => Promise<any>
}

const API_KEY = getApiKey();

export const TOOL_DEFINITIONS: Tool[] = [
    {
        definition: {
            "type": 'function',
            function: {
                "name": "verify_code",
                "description": "Submit the answer to the scoring system",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "answer": {
                            type: "string",
                            description: "provide the answer candidate"

                        }
                    },
                    "required": ["answer"]
                }
            }
        },
        handler: async (confirmation: string) => {
            return await submit('firmware', {confirmation})
        }
    },
    {
        definition: {
            "type": 'function',
            function: {
                "name": 'run_shell',
                "description": 'Run the remote shell command',
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cmd": {
                            "type": "string",
                            "description": "command to execute"
                        }
                    },
                    required: ["cmd"]
                }
            }
        },
        handler: async (rawCmd: string) => {
            const cmd = sanitizeEditlineCommand(rawCmd);
            if (FORBIDDEN_DIRECTORIES.some(path => cmd.includes(path))) {
                throw new Error(`Forbidden directory in the command: ${cmd}. Stopping execution. Forbidden directories ${FORBIDDEN_DIRECTORIES}`)
            }
            validateCommand(cmd, ALLOWED_COMMANDS); // throws if something is off.

            const response = await apiPost<CommandResponse>('/api/shell', { apikey: API_KEY, cmd })
            if (cmd.trim().toLowerCase() === 'help') {
                await learnCommandsFromHelp(response)
            };
            trackGitignoredPaths(cmd, response);
            warnOnReboot(cmd, response);
            return response;
        }
    },
    {
        definition: {
            "type": 'function',
            function: {
                "name": 'set_timeout',
                "description": 'Run to set timeout',
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timeout": {
                            "type": "number",
                            "description": "numbers of seconds to wait before firing next command"
                        }
                    },
                    required: ["timeout"]
                }
            }
        },
        handler: async (timeout) => {
             await setTimeout(timeout * 1000);
             return `waited for ${timeout}s. Retry the last command`;
        }
    }
];

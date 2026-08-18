import { apiPost, getApiKey, submit } from "../../api";
import { setTimeout } from 'node:timers/promises';
import { llm } from "../../llm";


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

export type CommandResponse = {
    code: number,
    message: string,
    path?: string,
    data: any
}

type CommandSpec = {
    name: string,
    args: { name: string, required: boolean }[],
    flags: string[]
}

const FORBIDDEN_DIRECTORIES = [
    'etc', 'root', 'proc'
]

const ALLOWED_COMMANDS: CommandSpec[] = [
    { name: 'help', args: [], flags: [] }
];

const API_KEY = getApiKey();


// The model consistently wraps editline's replacement content in quotes (e.g.
// `editline settings.ini 2 "enabled=true"`), and this shell stores the quotes
// literally, corrupting the line. Strip one matching pair before it's sent.
const sanitizeEditlineCommand = (cmd: string): string => {
    const [keyword, file, lineNumber, ...contentParts] = cmd.trim().split(/\s+/);
    if (keyword?.toLowerCase() !== 'editline' || contentParts.length === 0) return cmd;

    let content = contentParts.join(' ');
    const isQuoted = (content.startsWith('"') && content.endsWith('"'))
        || (content.startsWith("'") && content.endsWith("'"));
    if (isQuoted) content = content.slice(1, -1);

    return [keyword, file, lineNumber, content].join(' ');
}

const validateCommand = (cmd: string, specs: CommandSpec[]): boolean => {
    const [name, ...tokens] = cmd.trim().split(/\s+/);

    // A bare path (e.g. running a binary directly, "/opt/.../cooler.bin admin1") isn't a
    // shell builtin from `help` — this shell executes files by typing their path directly.
    if (name.startsWith('/') || name.startsWith('./')) return true;

    const commandSpec = specs.find(spec => spec.name === name);
    if (!commandSpec) {
        throw new Error(`Unkown command: ${name}`);
    }
    // if it's valid, let's check tokens.
    for (const token of tokens) {
        if (token.startsWith('-') && !commandSpec.flags.includes(token)) {
            throw new Error(`The spec for the ${commandSpec.name} doesn't include flags. You provided: ${cmd}. Supported spec: ${JSON.stringify(commandSpec)}`);
        }

    }

    return true;
}

const COMMAND_LIST_FORMAT = {
    name: 'commands',
    strict: true,
    schema: {
        type: 'object',
        properties: {
            commands: {
                type: 'array',
                items: {
                    type: 'object',
                    properties: {
                        name: {
                            type: 'string',
                            description: 'name of the command'
                        },
                        args: {
                            type: 'array',
                            description: 'positional arguments the command accepts',
                            items: {
                                type: 'object',
                                properties: {
                                    name: { type: 'string' },
                                    required: { type: 'boolean' }
                                },
                                required: ['name', 'required'],
                                additionalProperties: false
                            }
                        },
                        flags: {
                            type: 'array',
                            description: 'flag tokens the command accepts, e.g. "-R"',
                            items: { type: 'string' }
                        }
                    },
                    required: ['name', 'args', 'flags'],
                    additionalProperties: false
                }
            }
        },
        required: ['commands'],
        additionalProperties: false
    }
};

const learnCommandsFromHelp = async (helpOutput: CommandResponse): Promise<void> => {
    const response = await llm([
        {
            role: 'user', content: `
            From the provided response, extract the list of available commands.
            ${JSON.stringify(helpOutput)}
            If a command takes no flags or positional args, use an empty array for that field.
            `
        }
    ], { responseFormat: COMMAND_LIST_FORMAT });

    const { commands } = JSON.parse(response.message.content) as { commands: CommandSpec[] };
    ALLOWED_COMMANDS.push(...commands);
}

const trackGitignoredPaths = (cmd: string, response: CommandResponse): void => {
    if (!cmd.includes('.gitignore') || !response.data) return;
    for (const rawLine of response.data.split('\n')) {
        const path = rawLine.trim().replace(/\/$/, ''); // drop trailing "/" so "logs/" also matches "cat logs/x" and "ls logs"
        if (!path || path.startsWith('#')) continue; // skip blank lines and comments — an empty string would match every command
        FORBIDDEN_DIRECTORIES.push(path);
    }
}

let rebootCount = 0;

const warnOnReboot = (cmd: string, response: CommandResponse): void => {
    if (cmd.trim().toLowerCase() !== 'reboot') return;
    rebootCount++;
    // Appended to .data (not .message) — that's the field the model actually sees in the
    // tool result content, per main-auto.ts's push site.
    response.data = `${response.data}\n\nNote: this is reboot #${rebootCount} this session. Rebooting wipes all files and progress on the VM — only do this when you're certain you made a destructive, unrecoverable change to a file or permission. A rejected command, a 404, or a validation error means nothing was sent to the VM at all — that is not a reason to reboot.`;
}

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
             return `waited for ${timeout*1000}s. Retry the last command`;
        }
    }
];
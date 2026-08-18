import { llm } from "../../llm";

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

export const FORBIDDEN_DIRECTORIES = [
    'etc', 'root', 'proc'
]

export const ALLOWED_COMMANDS: CommandSpec[] = [
    { name: 'help', args: [], flags: [] }
];

// The model consistently wraps editline's replacement content in quotes (e.g.
// `editline settings.ini 2 "enabled=true"`), and this shell stores the quotes
// literally, corrupting the line. Strip one matching pair before it's sent.
export const sanitizeEditlineCommand = (cmd: string): string => {
    const [keyword, file, lineNumber, ...contentParts] = cmd.trim().split(/\s+/);
    if (keyword?.toLowerCase() !== 'editline' || contentParts.length === 0) return cmd;

    let content = contentParts.join(' ');
    const isQuoted = (content.startsWith('"') && content.endsWith('"'))
        || (content.startsWith("'") && content.endsWith("'"));
    if (isQuoted) content = content.slice(1, -1);

    return [keyword, file, lineNumber, content].join(' ');
}

export const validateCommand = (cmd: string, specs: CommandSpec[]): boolean => {
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

export const learnCommandsFromHelp = async (helpOutput: CommandResponse): Promise<void> => {
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

export const trackGitignoredPaths = (cmd: string, response: CommandResponse): void => {
    if (!cmd.includes('.gitignore') || !response.data) return;
    for (const rawLine of response.data.split('\n')) {
        const path = rawLine.trim().replace(/\/$/, ''); // drop trailing "/" so "logs/" also matches "cat logs/x" and "ls logs"
        if (!path || path.startsWith('#')) continue; // skip blank lines and comments — an empty string would match every command
        FORBIDDEN_DIRECTORIES.push(path);
    }
}

let rebootCount = 0;

export const warnOnReboot = (cmd: string, response: CommandResponse): void => {
    if (cmd.trim().toLowerCase() !== 'reboot') return;
    rebootCount++;
    // Appended to .data (not .message) — that's the field the model actually sees in the
    // tool result content, per main-auto.ts's push site.
    response.data = `${response.data}\n\nNote: this is reboot #${rebootCount} this session. Rebooting wipes all files and progress on the VM — only do this when you're certain you made a destructive, unrecoverable change to a file or permission. A rejected command, a 404, or a validation error means nothing was sent to the VM at all — that is not a reason to reboot.`;
}

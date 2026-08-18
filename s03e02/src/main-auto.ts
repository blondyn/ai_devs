import { readFile, stat } from "fs/promises"
import { setTimeout } from 'node:timers/promises';
import matter from "gray-matter"
import { TOOL_DEFINITIONS } from "./tools"
import { join } from "path"
import { llm, getUsageStats } from "../../llm"
import { Logger } from "./logger";
export interface GoalTemplate {
    content: string
    tools: string[]
}

export interface ToolCall {
    id: string,
    type: string,
    function: {
        name: string,
        arguments: string
    }
}

export interface ToolCallResponse {
    role: 'tool',
    toolCallId: string,
    name: string,
    content: string
}

const MAX_TURNS = 50;
const ENABLE_PERIODIC_REFLECTION = true;
const REFLECTION_INTERVAL = 10;

export const logger = new Logger({
    artifactDirectory: 'artifacts',
    level: 'info',
    sinks: ['console']
});

export const loggerFile = new Logger({
    artifactDirectory: 'artifacts',
    level: 'info',
    sinks: ['file']
})

async function readGoal(fileName: string): Promise<GoalTemplate> {
    const PROJECT_ROOT = process.cwd()
    const PATH = join(PROJECT_ROOT, fileName)
    if (!(await stat(PATH)).isFile()) {
        throw new Error(`${fileName} doesn't exist`);
    }

    const raw = await readFile(PATH);
    const parsed = matter(raw)
    return {
        content: parsed.content.trim(),
        tools: parsed.data.tools
    }
}

function buildTools(tool_names: string[]): any {
    return TOOL_DEFINITIONS.filter(tool => tool_names.includes(tool.definition.function.name)).map(tool => tool.definition);
}

const MAX_TOOL_RESULT_CHARS = 4000;
const HISTORY_MESSAGES_KEPT_AFTER_OVERFLOW = 6;

function truncateForContext(text: string): string {
    if (text.length <= MAX_TOOL_RESULT_CHARS) return text;
    return `${text.slice(0, MAX_TOOL_RESULT_CHARS)}\n... [truncated ${text.length - MAX_TOOL_RESULT_CHARS} more characters — command output was too large]`;
}

function isContextLengthError(err: any): boolean {
    return typeof err?.message === 'string' && err.message.includes('maximum context length');
}

const summarizeHistory = async (messages: Record<string, unknown>[]): Promise<string> => {
    const response = await llm([
        {
            role: 'user', content: `
            Summarize this agent transcript (shell commands run, their results, and any conclusions) into a compact briefing so the agent can continue the task without re-exploring what it already knows.
            Preserve: passwords/credentials found, file paths explored, command syntax discovered, edits already made to files, and what has NOT worked yet.
            Omit: full raw command output, repeated failed attempts with the same result.
            Keep it under 400 words, plain text, no markdown.

            ${JSON.stringify(messages)}
            `
        }
    ], { maxTokens: 800 });
    return response.message.content;
}

// Finds the earliest index >= 1 that doesn't start mid-way through an assistant/tool_calls
// group — a 'tool' message must always be preceded by the assistant message that issued it,
// or the next llm() request 400s on a dangling tool_call_id.
const findSafeSplitIndex = (messageHistory: Record<string, unknown>[], desiredIndex: number): number => {
    let index = desiredIndex;
    while (index > 1 && messageHistory[index]?.role === 'tool') index--;
    return index;
}

async function compactHistoryAfterOverflow(messageHistory: Record<string, unknown>[]): Promise<void> {
    const system = messageHistory[0];
    const splitIndex = findSafeSplitIndex(messageHistory, Math.max(1, messageHistory.length - HISTORY_MESSAGES_KEPT_AFTER_OVERFLOW));
    const olderMessages = messageHistory.slice(1, splitIndex);
    const recentMessages = messageHistory.slice(splitIndex);

    let summaryNote: string;
    try {
        const summary = await summarizeHistory(olderMessages);
        summaryNote = `Earlier progress was summarized because history exceeded the context limit:\n\n${summary}`;
    } catch (err: any) {
        logger.error(`History summarization failed, falling back to a plain drop: ${err.message ?? err}`);
        summaryNote = 'Earlier history was dropped because it exceeded the model\'s context limit — a previous command likely returned too much data. Avoid dumping full file contents into the shell; check size or read in chunks instead.';
    }

    messageHistory.length = 0;
    messageHistory.push(system, { role: 'user', content: summaryNote }, ...recentMessages);
}

const printSessionStats = (): void => {
    const stats = getUsageStats();
    logger.info(
        `Session stats — queries: ${stats.queries}, prompt tokens: ${stats.promptTokens}, completion tokens: ${stats.completionTokens}, total tokens: ${stats.totalTokens}`
    );
    logger.artifact('session-stats.json', JSON.stringify(stats, null, 2));
}

const reflect = async (messageHistory: Record<string, unknown>[]): Promise<void> => {
    messageHistory.push({
        role: 'user', content: `
        Pause before continuing. In under 150 words, state:
        1. What you've learned so far.
        2. Your current hypothesis for solving the task.
        3. The next concrete step, and why.
        Do not call a tool for this message — just respond with text.
        `
    });
    const response = await llm(messageHistory, {});
    messageHistory.push({ role: 'assistant', content: response.message.content });
    // Leave history ending on a 'user' turn — an assistant->assistant turn (this reply,
    // immediately followed by the next loop iteration's tool-calling llm() call) is what
    // was producing empty completions.
    messageHistory.push({ role: 'user', content: 'Now continue the task — call the appropriate tool for your next step.' });
    logger.info('Reflection', response.message.content);
}

async function runAgent(goal: string, tools: string[]) {
    const messageHistory: Record<string, unknown>[] = [
        { 'role': 'system', content: JSON.stringify(goal) }
    ];

    const saveHistory = () => logger.artifact('message-history.json', JSON.stringify(messageHistory));
    process.on('exit', saveHistory);
    process.on('SIGINT', () => { saveHistory(); process.exit(0); });
    process.on('SIGTERM', () => { saveHistory(); process.exit(0); });

    for (let i = 0; i < MAX_TURNS; i++) {
        if (ENABLE_PERIODIC_REFLECTION && i > 0 && i % REFLECTION_INTERVAL === 0) {
            try {
                await reflect(messageHistory);
            } catch (err: any) {
                logger.error(`Reflection step failed, skipping: ${err.message ?? err}`);
            }
        }

        let response;
        try {
            response = await llm(messageHistory, { tools: buildTools(tools), maxTokens: 4096 });
        } catch (err: any) {
            if (isContextLengthError(err)) {
                logger.error('Context length exceeded — compacting history and retrying');
                await compactHistoryAfterOverflow(messageHistory);
            } else {
                logger.error(`LLM request failed (not a VM issue): ${err.message ?? err}`);
                messageHistory.push({
                    role: 'user',
                    content: `The request to the model failed — this has nothing to do with the VM, nothing was sent to it: ${err.message ?? err}`
                });
            }
            await setTimeout(1000);
            continue;
        }

        const toolCalls = response.message.tool_calls;
        logger.info(
            `running ${i} iteration (finish_reason: ${response.finish_reason})`,
            toolCalls ? toolCalls[0].function : response.message
        );
        if (toolCalls != null) {
            messageHistory.push(response.message);

            for (const call of toolCalls as ToolCall[]) {
                const handler = TOOL_DEFINITIONS.find(tool => tool.definition.function.name === call.function.name)?.handler;
                if (handler == null) continue;
                try {
                    const fnArgs = Object.values(JSON.parse(call.function.arguments)) as [arg: any];
                    const result = await handler.apply(null, fnArgs);
                    logger.info(JSON.stringify(result, null, 2));
                    if (result != null) {
                        messageHistory.push({
                            role: 'tool',
                            toolCallId: call.id,
                            name: call.function.name,
                            content: truncateForContext(JSON.stringify(result?.data ?? result))
                        });
                    }
                    if (call.function.name === 'verify_code' && result?.code === 0) {
                        logger.info(`Task complete — verify_code succeeded: ${result.message}`);
                        printSessionStats();
                        return;
                    }
                } catch (err: any) {
                    const isLocalRejection = !err.code && !err.body;
                    let content = isLocalRejection
                        ? `Command rejected before it reached the VM: ${err.message ?? err}\nThe VM's state is unchanged — this is not a reason to reboot.`
                        : `Error returned from the VM shell API. Act on the error appropriately
                            ${err.code ? `HTTP error code: ${err.code}` : ''}
                            ${err.body != null ? `message: ${JSON.parse(err.body).message}` : ''}`;
                    if (err.code === 429) {
                        content += '\nset timeout to 20s';
                    } else if (err.code === 404) {
                        content += '\nfile not found. Don\'t search for it again — this does not mean the VM is broken, do not reboot for a missing path.';
                    }
                    logger.error(content)
                    messageHistory.push({ role: 'user', content })
                }
            }
        } else if (response.message.content) {
            logger.info('successful message', response.message);
            messageHistory.push({ role: 'assistant', content: response.message.content });
        } else {
            logger.error('Empty response from the model — no tool call and no text');
            messageHistory.push({
                role: 'user',
                content: 'Your last response was empty — no tool call and no text. You must either call a tool or reply with text. Continue the task.'
            });
        }
        await setTimeout(1000);
    }
    logger.info(`Reached MAX_TURNS (${MAX_TURNS}) without a successful verify_code call.`);
    printSessionStats();
}


(async function main_auto() {
    const goal = await readGoal('goal.md');
    if(goal.content == null) {
        throw new Error('empty file');
    }
    // logger.info(goal.content, JSON.stringify(goal.tools));
    await runAgent(goal.content, goal.tools);
})()
    .catch(err => { console.error(err); process.exit(1); });

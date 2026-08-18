import { llm } from "../../llm";
import { logger } from "./logging";

const MAX_TOOL_RESULT_CHARS = 4000;
const HISTORY_MESSAGES_KEPT_AFTER_OVERFLOW = 6;

export function truncateForContext(text: string): string {
    if (text.length <= MAX_TOOL_RESULT_CHARS) return text;
    return `${text.slice(0, MAX_TOOL_RESULT_CHARS)}\n... [truncated ${text.length - MAX_TOOL_RESULT_CHARS} more characters — command output was too large]`;
}

export function isContextLengthError(err: any): boolean {
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

export async function compactHistoryAfterOverflow(messageHistory: Record<string, unknown>[]): Promise<void> {
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

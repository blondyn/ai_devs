import { llm, getUsageStats } from "../../llm";
import { logger } from "./logging";

export const printSessionStats = (): void => {
    const stats = getUsageStats();
    logger.info(
        `Session stats — queries: ${stats.queries}, prompt tokens: ${stats.promptTokens}, completion tokens: ${stats.completionTokens}, total tokens: ${stats.totalTokens}`
    );
    logger.artifact('session-stats.json', JSON.stringify(stats, null, 2));
}

export const reflect = async (messageHistory: Record<string, unknown>[]): Promise<void> => {
    messageHistory.push({
        role: 'user', content: `
        Pause before continuing. In under 150 words, state:
        1. What you've learned so far.
        2. Your current hypothesis for solving the task.
        3. The next concrete step, and why.
        4. Re-read the task's stated goal (in the system prompt). Is your current line of investigation actually working toward that specific goal, or has it drifted onto something else you found along the way that only seemed relevant? If it has drifted, say so and correct course now.
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

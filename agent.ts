import { readFileSync, writeFileSync } from 'fs';
import matter from 'gray-matter';
import { llm } from './llm';
import { prepTools, tool_call, resizeIfNeeded } from './tools';

export async function startAgent(agent: string, startingMessage?: string): Promise<any> {
    const raw = readFileSync(`workflows/${agent}.md`, 'utf-8');
    const { data, content } = matter(raw);
    const messages: Record<string, unknown>[] = [
        { role: 'system', content },
    ];
    if (startingMessage != null) {
        messages.push({ role: 'assistant', content: startingMessage });
    }

    let i = 0;
    while (i++ < 10) {
        const response = await llm(messages, { tools: prepTools(data.tools), model: data.model });
        const { message, finish_reason } = response;
        console.log({ message, tool_call: JSON.stringify(message.tool_calls) });

        if (finish_reason === 'tool_calls') {
            for (const tool of message.tool_calls) {
                console.log(`calling ${tool.function.name} ${tool.function.arguments}`);
                const toolResponse = await tool_call(tool.function.name, tool.function.arguments);

                if (toolResponse instanceof ArrayBuffer) {
                    const resized = await resizeIfNeeded(Buffer.from(toolResponse));
                    writeFileSync('output.png', resized);
                    messages.push({
                        role: 'tool',
                        tool_call_id: tool.id,
                        content: [{ type: 'input_image', image_url: { url: `data:image/png;base64,${resized.toString('base64')}` } }],
                    });
                } else {
                    messages.push({
                        role: 'tool',
                        tool_call_id: tool.id,
                        content: toolResponse,
                    });
                }
            }
        } else if (finish_reason === 'stop') {
            messages.push({ role: message.role, content: message.content });
            return message.content;
        } else {
            console.log({ response });
        }
    }
}

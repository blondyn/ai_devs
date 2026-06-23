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
        messages.push({ role: 'user', content: startingMessage });
    }

    let i = 0;
    while (i++ < 10) {
        const response = await llm(messages, { tools: prepTools(data.tools), model: data.model });
        const { message, finish_reason } = response;
        writeFileSync(`${agent}_history.json`, JSON.stringify(messages, null, 2));
        messages.push(message);

        if (finish_reason === 'tool_calls') {
            for (const tool of message.tool_calls) {
                console.log(`calling ${tool.function.name} ${tool.function.arguments}`);
                const toolResponse = await tool_call(tool.function.name, tool.function.arguments);
                if (toolResponse instanceof ArrayBuffer) {
                    const resized = await resizeIfNeeded(Buffer.from(toolResponse));
                    writeFileSync('output.jpeg', resized);
                    messages.push({
                        role: 'tool',
                        tool_call_id: tool.id,
                        content: [{ type: 'input_image', image_url: { url: `data:image/jpeg;base64,${resized.toString('base64')}` } }],
                    });
                } else {
                    messages.push({
                        role: 'tool',
                        tool_call_id: tool.id,
                        content: typeof toolResponse === 'string' ? toolResponse : JSON.stringify(toolResponse),
                    });
                }
            }
        } else if (finish_reason === 'stop') {
            console.log({[agent]: message.content});
            messages.push({ role: message.role, content: message.content });
            return message.content;
        } else {
            console.log({ response });
            return response
        }
    }
}

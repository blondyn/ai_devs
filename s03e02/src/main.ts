/// <reference path="./marked-terminal.d.ts" />
import { config } from 'dotenv';
import { resolve } from 'path';
import { apiPost, getApiKey, llm } from '../../common';

config({ path: resolve(__dirname, '../../.env') });
import readline from 'readline';
import { marked } from 'marked';
import { markedTerminal } from 'marked-terminal';

marked.use(markedTerminal() as any);

type CommandResponse = {
    code: number,
    message: string,
    path?: string,
    data: any
}
function ask(rl: readline.Interface, prompt: string): Promise<string> {
    return new Promise(resolve => rl.question(prompt, resolve));
}


function createLLMQuery(context: string, lastExecutedCommandMem?: CommandResponse | null): { role: string, content: string } {
    // let llm handle the response. 
    const messageSplit = context.trim().toLowerCase().split(' ');
    let query = null;
    // parse the last message.
    if (messageSplit.length > 1) {
        // custom question
        const userQuestion = messageSplit.slice(1).join(' ');
        console.log("sending a custom query to llm... " + userQuestion)
        query = {
            role: 'user',
            content: userQuestion
        };
    } else {
        console.log('querying llm with the last api response...' + lastExecutedCommandMem?.message);
        query = {
            role: 'user', content: `
                        The following message was returned from the API call:
                        ${lastExecutedCommandMem?.message}
                        ${lastExecutedCommandMem?.data ? `
                            The following data was returned from the API call:
                            ${lastExecutedCommandMem?.data}
                        ` : ''}

                        Suggest the next step the user should take, and which command to run
                    `}
    }
    return query;

}


async function main() {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.once('SIGINT', () => {
        process.off('SIGINT', () => {
            rl.close();
        })
    })
    let lastExecutedCommandMem: CommandResponse | null = null;
    const messageHistory: Record<string, unknown>[] = [];
    while (true) {
        try {
            const answer = await ask(rl, '\nYou:');
            if (answer.trim().toLowerCase() === 'exit') {
                process.exit();
            };
            if (answer.trim().toLowerCase().startsWith('llm')) {
                // let llm handle the response. 
                messageHistory.push(createLLMQuery(answer.trim().toLowerCase(), lastExecutedCommandMem))
                const llmResponse = await llm(messageHistory, { fullResponse: true });
                // stats
                console.log({
                    model: llmResponse.model,
                    cost: llmResponse.usage.cost,
                    costDetails: llmResponse.usage.costDetails
                })

                // response
                const suggestion = llmResponse.choices[0].message.content;
                console.log('\nSuggestion:\n' + await marked.parse(suggestion));

                continue;
            }

            lastExecutedCommandMem = await executeCommand(answer);
            // push the data to context for llm further exploration
            messageHistory.push(
                {
                    role: 'user',
                    content: `
                for the command: ${answer}
                    we got the following response:
                    ${JSON.stringify(lastExecutedCommandMem)}
                `
                }
            )
            console.log({ msg: lastExecutedCommandMem.message, data: lastExecutedCommandMem.data });
        } catch (error: any) {

            console.log("Caught error");
            // http code
            if (error.code === 429) {
                // slow down
                console.log('wait a sec');
            } else if (error.code === 404) {
                console.log('file not found');
            } else if (error.code === 403) {
                console.log('forbidden access');
            }
            console.log({ message: JSON.parse(error.body)?.message });
            lastExecutedCommandMem = {
                code: error.code,
                message: error.message,
                data: null
            }

        }
    }
}

const executeCommand = async (cmd: string): Promise<CommandResponse> => {
    const apiKey = getApiKey();
    return await apiPost<CommandResponse>('/api/shell', { apikey: apiKey, cmd })
}

main().catch(err => { console.error(err); process.exit(1); });

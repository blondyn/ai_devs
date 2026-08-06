import { config } from 'dotenv';
import { resolve } from 'path';
import { readSensorsZip, SensorComponent, SensorEntry } from './tools';
import { submit } from '../../api';
config({ path: resolve(__dirname, '../../.env') });

const constraints: Map<SensorComponent, [number, number]> = new Map([
    ["temperature", [553, 873]],
    ["humidity", [40, 80]],
    ["pressure", [60, 160]],
    ["voltage", [229, 231]],
    ["water", [5, 15]],
]);

const sensorToFieldMapping: Record<SensorComponent, string> = {
    "temperature": "temperature_K",
    "humidity": "humidity_percent",
    "pressure": "pressure_bar",
    "voltage": "voltage_supply_v",
    "water": "water_level_meters"
}

const isWithinGuardrail = (entry: SensorEntry) => {
    return (entry.sensor_type.split("/") as SensorComponent[]).every(sensor_type => {
        const field = sensorToFieldMapping[sensor_type] as keyof SensorEntry;
        const range = constraints.get(sensor_type);
        if (!range) return false;
        const [min, max] = range;
        return (entry[field] as number) >= min && (entry[field] as number) <= max;
    });
}

const misreportedData = (entry: SensorEntry) => {
    // for each sensor, check the type; 
    // then check if values for other types not mentioned in the type are not set (should be 0)
    const sensorTypes = new Set((entry.sensor_type.split('/') as SensorComponent[]));
    const sensorTypesToCheck = (Object.keys(sensorToFieldMapping) as SensorComponent[]).filter((sensorField) => !sensorTypes.has(sensorField));
    return sensorTypesToCheck.some(typeCheck => {
        const entryKey = sensorToFieldMapping[typeCheck] as keyof SensorEntry;
        return (entry[entryKey] as number) !== 0;
    });
}

const classifyErronousInterpretation = async (entries: Map<string, string[]>): Promise<ClassificationResult | null> => {
    try {
        console.log(`firing request with ${entries.size} element map`)
        const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
            method: 'POST',
            headers: {
                Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                model: 'openai/gpt-4o-mini',
                messages: [
                    { role: 'user', content: 'Classify messages based on the string provided. In negative_feedback we should find messages identifying a problem with the sensor reading or any problem' },
                    { role: 'user', content: `Here are operator notes, each mapped to every sensor id that shares that exact note text:\n\`\`\`json\n${JSON.stringify([...entries].map(([note, ids]) => ({ note, ids })))}\n\`\`\`\n\nFor each note matching the category, return ALL of its ids in negative_feedback — not just one per note.` }
                ],
                response_format: {
                    type: 'json_schema',
                    json_schema: {
                        name: 'results',
                        schema: {
                            type: 'object',
                            properties: {
                                negative_feedback: {
                                    type: 'array',
                                    items: { type: 'string' }
                                },
                                // positive_feedback: {
                                //     type: 'array',
                                //     items: { type: 'string' }
                                // }
                            },
                            required: ['negative_feedback']
                        },
                    }
                }
            })
        });

        if (!response.ok) {
            // console.error(response);
            const error = await response.text();
            throw new Error(`${response.status} ${error}`);
        }
        const jsonResponse = await response.json();
        return parseResponse(jsonResponse);
    } catch (e: any) {
        return Promise.reject(e);
    }

}
type ClassificationResult = {
    positive_feedback: string[],
    negative_feedback: string[]
}

const parseResponse = (response: any): ClassificationResult => {
    const content = response.choices[0].message.content;
    const parsed = JSON.parse(content);
    return {
        negative_feedback: parsed.negative_feedback,
        positive_feedback: parsed.positive_feedback
    }
}


function getDuplicatedOperatorNotes(sensors: Map<string, SensorEntry>) {
    return Array.from(sensors.entries()).reduce((acc, [key, entry]) => {
        let keys = [key];
        if (acc.has(entry.operator_notes)) {
            const existingKeys = acc.get(entry.operator_notes);
            if (existingKeys != null) {
                keys = keys.concat(existingKeys);
            }
        }
        acc.set(entry.operator_notes, keys);
        return acc;
    }, new Map<string, string[]>())
}

const chunk = <T>(items: T[], size: number): T[][] => {
    const chunks = [];
    for (let i = 0; i < items.length; i += size) {
        chunks.push(items.slice(i, i + size))
    }
    return chunks;
}

async function main() {
    console.log('Downloading sensors.zip...');
    const sensors = await readSensorsZip();
    console.log(`Loaded ${sensors.size} sensor files`);


    // invalid check
    const invalidDataReadsIds = new Set([...sensors].filter(([_key, entry]) => !isWithinGuardrail(entry) || misreportedData(entry)).map(([key]) => key));

    // valid checks
    const validDataReads = new Map([...sensors].filter(([key]) => !invalidDataReadsIds.has(key)));

    // remove the invalid subset
    const duplicates = getDuplicatedOperatorNotes(validDataReads)
    const chunked = chunk(Array.from(duplicates), 300);

    const chunkedRequests = chunked.map(batch => classifyErronousInterpretation(new Map(batch)))

    const settled = await Promise.allSettled(chunkedRequests);
    const data = settled
        .filter((r): r is PromiseFulfilledResult<ClassificationResult | null> => r.status === 'fulfilled')
        .map(r => r.value);
    const failedCount = settled.length - data.length;
    if (failedCount > 0) console.warn(`${failedCount} batch(es) failed to classify`);

    const negativeFeedback = new Set(data.flatMap(d => d?.negative_feedback ?? []));

    /*
    Jako anomalie definiujemy:
        - X dane pomiarowe nie mieszczą się w normach
        - operator twierdzi, że wszystko jest OK, ale dane są niepoprawne (false negative)
        - X operator twierdzi, że znalazł błędy, ale dane są OK (false positive)
        - X czujnik zwraca dane, których nie powinien zwracać (np. czujnik poziomu wody zwraca napięcie prądu)
    */
    // // verify
    const payload = [
        ...invalidDataReadsIds,
        ...negativeFeedback
    ]
    console.log({ payload })
    const response = await submit('evaluation', { "recheck": payload })
    console.log(response);
}

main().catch(err => { console.error(err); process.exit(1); });

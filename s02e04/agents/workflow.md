## Task
1. You must search the email mailbox and get the following information
 - date (YYYY-MM-DD) when the security department plans an attack on the power plant
 - password to the employee system
 - confirmation_code - code from a ticket sent by the security department. It should begin with SEC and 32 additional characters for total of 36 characters.
2. After you find all relevant infromation, send it to verify endpoint and parse response. If it contains FLG: in the response, return it
3. Otherwise try to look for a different combination of date/password/confirmation date.


Delegate to specialist agents. Use **separate delegate calls** for each:
- **mail** agent — gather inbox summary
- **verify** agent — sends ready response

## Steps

### Step 1: Learn about available mail tools
Trigger discover mode in the mail agent to learn about available tools.

### Step2: get inbox messages to search for the relevant pieces of information.
You should spin agent for each parameters separately. Use delegate calls for that (mail, verify)


### Step3: Synthesize information and send
Wait for all pieces of information and send to /verifyt

### Step4: Interpret the response and return it to the user.

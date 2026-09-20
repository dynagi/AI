# FinPilot: What Is Happening So Far (Simple Version)

## What is FinPilot?

FinPilot is like a smart helper for your money. It looks at your income and spending, then answers questions like:

- "Why did I spend more this month?"
- "Which subscriptions am I paying for?"
- "Am I on track to save for a new laptop?"

It does **not** tell you what to invest in. It only explains your own money, using your own numbers.

## How does it get your money data?

There are two ways:

1. **Connect a bank (demo only).** You click "Connect Demo Bank", and FinPilot asks for your permission, like a real bank app would. After you approve, it loads **pretend** bank data. It never touches a real bank account and never asks for passwords, PINs or OTPs.
2. **Type it in yourself.** You can add a transaction by hand, or upload a spreadsheet (CSV file) with many transactions.

Both ways end up in the same place. The helper doesn't care where the data came from.

## What FinPilot does with the data

1. **Sorts each transaction** into a group like Food, Shopping, Transport or Rent. If it gets one wrong, you can fix it, and it remembers your fix next time.
2. **Spots regular payments** like Netflix, rent and insurance, and shows them separately.
3. **Notices unusual spending**, for example "Shopping is 34% higher than usual". It only states facts and never tells you what to do.
4. **Makes a monthly summary** of income, spending, savings and where the money went.
5. **Tracks budgets**, like "Food: ₹5,000 a month", and shows how much you've used.
6. **Tracks savings goals**, like "₹60,000 laptop in 6 months", and shows whether your current saving pace can get you there.
7. **Answers your questions in chat** ("Ask FinPilot"). It looks up your real numbers before it answers, so it doesn't guess.

## What has been built and tested

- Sign up and sign in
- The demo bank connection with the permission screen
- Adding transactions by hand and uploading a CSV
- Sorting, regular-payment detection and unusual-spending detection
- Budgets and goals
- Pages: Dashboard, Ask FinPilot, Transactions, Budgets, Goals, Data Sources, Settings
- **Privacy:** one user can never see another user's data. This was tested and works.

I tested all of this by calling the app directly. I have not clicked through the screens in a browser.

## What is not finished or not tested

- **The chat needs your Gemini key.** Without it the chat says "AI assistant unavailable". I couldn't test the real chat answers, so please try it once you add your key.
- **Real bank connection (Setu)** is prepared but switched off. The demo uses pretend data. A real connection needs Setu's approval process.
- **Uploading a PDF bank statement** is not built. Typing and CSV upload work.

## What you need to do next

1. Get a free Gemini key from https://aistudio.google.com/apikey.
2. Paste it into the `.env` file next to `GEMINI_API_KEY=`.
3. Run `npm run dev` and open http://localhost:3000.
4. Follow the demo steps in `README.md`.

## Where things are stored

Everything is saved in one small file on your computer (`prisma/dev.db`). You don't need to install a separate database.

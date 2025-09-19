const axios = require('axios');
const chalk = require('chalk').default;
const CONFIG = require('./config');

async function getNewsSentiment(symbol) {
    if (!CONFIG.newsApiKey) {
        return null;
    }

    try {
        const response = await axios.get('https://newsapi.org/v2/everything', {
            params: {
                q: symbol,
                apiKey: CONFIG.newsApiKey,
                language: 'en',
                sortBy: 'publishedAt',
                pageSize: 5
            }
        });

        if (response.data.articles && response.data.articles.length > 0) {
            // In a real application, you would perform sentiment analysis on the articles.
            // For this placeholder, we'll just use the title of the most recent article.
            const latestArticle = response.data.articles[0];
            return {
                sentiment: "Neutral", // Placeholder sentiment
                source: latestArticle.source.name,
                title: latestArticle.title
            };
        }
        return null;
    } catch (error) {
        console.error(chalk.red(`   (Failed to fetch news: ${error.message})`));
        return null;
    }
}

module.exports = { getNewsSentiment };
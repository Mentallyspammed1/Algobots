const readline = require('readline');
const { color, colors } = require('./logger');

async function promptUser(question, defaultAnswer = 'n') {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise(resolve => {
    rl.question(color(question, colors.neonOrange), ans => {
      rl.close();
      resolve(ans.toLowerCase().trim() || defaultAnswer.toLowerCase());
    });
  });
}

module.exports = {
    promptUser,
};

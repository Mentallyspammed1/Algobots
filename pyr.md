async function timeout(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function upgradeTool(toolId, newVersion) {
  console.log(`Starting upgrade for tool ${toolId} to version ${newVersion}...`);
  await timeout(Math.random() * 2000 + 500); // Simulate upgrade time
  console.log(`Tool ${toolId} upgraded to version ${newVersion}.`);
  return { toolId, version: newVersion, status: 'upgraded' };
}

async function upgradeTools(toolsToUpgrade) {
  const upgradePromises = toolsToUpgrade.map(tool => upgradeTool(tool.id, tool.newVersion));
  const results = await Promise.all(upgradePromises);
  console.log('All tool upgrades completed.');
  return results;
}

async function main() {
  const tools = [
    { id: 'tool-abc', newVersion: '2.1.0' },
    { id: 'tool-xyz', newVersion: '1.5.3' },
    { id: 'tool-123', newVersion: '3.0.1' }
  ];

  const upgradeResults = await upgradeTools(tools);
  console.log('\nUpgrade Summary:');
  upgradeResults.forEach(result => {
    console.log(`- ${result.toolId}: ${result.status} to ${result.version}`);
  });
}

main();

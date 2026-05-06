import 'dotenv/config';
import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  Client,
  Events,
  GatewayIntentBits,
  REST,
  Routes,
  SlashCommandBuilder,
} from 'discord.js';

const BOARD_SIZE = 15;
const EMPTY = '·';
const BLACK = '⚫';
const WHITE = '⚪';
const activeGames = new Map();

const command = new SlashCommandBuilder()
  .setName('gomoku')
  .setDescription('開始一場五子棋')
  .addUserOption((option) =>
    option.setName('opponent').setDescription('對手').setRequired(true)
  );

const client = new Client({ intents: [GatewayIntentBits.Guilds] });

function createGame(player1, player2) {
  return {
    board: Array.from({ length: BOARD_SIZE }, () => Array(BOARD_SIZE).fill(EMPTY)),
    players: [player1, player2],
    turn: 0,
    cursorRow: 7,
    cursorCol: 7,
    winner: null,
  };
}

function boardToText(game) {
  const header = `   ${Array.from({ length: BOARD_SIZE }, (_, i) => `${(i + 1).toString().padStart(2, ' ')}`).join(' ')}`;
  const rows = game.board
    .map((row, r) => `${(r + 1).toString().padStart(2, ' ')} ${row.map((cell, c) => (r === game.cursorRow && c === game.cursorCol ? `[${cell}]` : ` ${cell} `)).join('')}`)
    .join('\n');

  const turnUser = game.players[game.turn];
  const turnStone = game.turn === 0 ? BLACK : WHITE;
  const status = game.winner
    ? `🏆 勝者：<@${game.winner}>`
    : `目前回合：${turnStone} <@${turnUser}>\n游標：(${game.cursorRow + 1}, ${game.cursorCol + 1})`;

  return `# 五子棋\n${status}\n\n\`\`\`\n${header}\n${rows}\n\`\`\``;
}

function controls(disabled = false) {
  return [
    new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId('move_up').setLabel('⬆️').setStyle(ButtonStyle.Secondary).setDisabled(disabled),
      new ButtonBuilder().setCustomId('move_left').setLabel('⬅️').setStyle(ButtonStyle.Secondary).setDisabled(disabled),
      new ButtonBuilder().setCustomId('place').setLabel('落子').setStyle(ButtonStyle.Primary).setDisabled(disabled),
      new ButtonBuilder().setCustomId('move_right').setLabel('➡️').setStyle(ButtonStyle.Secondary).setDisabled(disabled),
      new ButtonBuilder().setCustomId('move_down').setLabel('⬇️').setStyle(ButtonStyle.Secondary).setDisabled(disabled)
    ),
    new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId('resign').setLabel('投降').setStyle(ButtonStyle.Danger).setDisabled(disabled)
    ),
  ];
}

function inBounds(v) {
  return v >= 0 && v < BOARD_SIZE;
}

function checkWin(board, row, col, stone) {
  const dirs = [[1, 0], [0, 1], [1, 1], [1, -1]];
  for (const [dr, dc] of dirs) {
    let count = 1;
    for (const sign of [-1, 1]) {
      let r = row + dr * sign;
      let c = col + dc * sign;
      while (inBounds(r) && inBounds(c) && board[r][c] === stone) {
        count += 1;
        r += dr * sign;
        c += dc * sign;
      }
    }
    if (count >= 5) return true;
  }
  return false;
}

client.once(Events.ClientReady, async (c) => {
  console.log(`Logged in as ${c.user.tag}`);

  const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_TOKEN);
  await rest.put(Routes.applicationCommands(process.env.CLIENT_ID), {
    body: [command.toJSON()],
  });
  console.log('Slash command registered');
});

client.on(Events.InteractionCreate, async (interaction) => {
  if (interaction.isChatInputCommand() && interaction.commandName === 'gomoku') {
    const opponent = interaction.options.getUser('opponent', true);

    if (opponent.bot) {
      return interaction.reply({ content: '不能和機器人對戰。', ephemeral: true });
    }

    if (opponent.id === interaction.user.id) {
      return interaction.reply({ content: '不能跟自己下棋。', ephemeral: true });
    }

    const game = createGame(interaction.user.id, opponent.id);
    activeGames.set(interaction.id, game);

    return interaction.reply({
      content: `<@${interaction.user.id}> vs <@${opponent.id}>\n${boardToText(game)}`,
      components: controls(),
    });
  }

  if (!interaction.isButton()) return;

  const game = activeGames.get(interaction.message.interaction?.id);
  if (!game) {
    return interaction.reply({ content: '這場對局已不存在。', ephemeral: true });
  }

  const currentPlayer = game.players[game.turn];
  if (interaction.user.id !== currentPlayer) {
    return interaction.reply({ content: '還沒輪到你。', ephemeral: true });
  }

  const move = interaction.customId;

  if (move === 'resign') {
    game.winner = game.players[(game.turn + 1) % 2];
    return interaction.update({
      content: `<@${game.players[0]}> vs <@${game.players[1]}>\n${boardToText(game)}`,
      components: controls(true),
    });
  }

  if (move === 'move_up') game.cursorRow = Math.max(0, game.cursorRow - 1);
  if (move === 'move_down') game.cursorRow = Math.min(BOARD_SIZE - 1, game.cursorRow + 1);
  if (move === 'move_left') game.cursorCol = Math.max(0, game.cursorCol - 1);
  if (move === 'move_right') game.cursorCol = Math.min(BOARD_SIZE - 1, game.cursorCol + 1);

  if (move === 'place') {
    if (game.board[game.cursorRow][game.cursorCol] !== EMPTY) {
      return interaction.reply({ content: '這格已經有棋子。', ephemeral: true });
    }

    const stone = game.turn === 0 ? BLACK : WHITE;
    game.board[game.cursorRow][game.cursorCol] = stone;

    if (checkWin(game.board, game.cursorRow, game.cursorCol, stone)) {
      game.winner = currentPlayer;
    } else {
      game.turn = (game.turn + 1) % 2;
    }
  }

  return interaction.update({
    content: `<@${game.players[0]}> vs <@${game.players[1]}>\n${boardToText(game)}`,
    components: controls(Boolean(game.winner)),
  });
});

if (!process.env.DISCORD_TOKEN || !process.env.CLIENT_ID) {
  throw new Error('請設定 DISCORD_TOKEN 與 CLIENT_ID 環境變數。');
}

client.login(process.env.DISCORD_TOKEN);

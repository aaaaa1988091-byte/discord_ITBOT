import 'dotenv/config';
import {
  ChannelType,
  Client,
  Events,
  GatewayIntentBits,
  PermissionFlagsBits,
  REST,
  Routes,
  SlashCommandBuilder,
} from 'discord.js';

const command = new SlashCommandBuilder()
  .setName('gomoku')
  .setDescription('在語音頻道建立五子棋通話活動邀請')
  .addChannelOption((option) =>
    option
      .setName('voice_channel')
      .setDescription('要開啟活動的語音頻道（不填則使用你目前所在頻道）')
      .addChannelTypes(ChannelType.GuildVoice)
      .setRequired(false)
  );

const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildVoiceStates] });

async function registerCommand() {
  const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_TOKEN);
  await rest.put(Routes.applicationCommands(process.env.CLIENT_ID), {
    body: [command.toJSON()],
  });
}

async function createActivityInvite(voiceChannelId) {
  const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_TOKEN);
  return rest.post(Routes.channelInvites(voiceChannelId), {
    body: {
      max_age: 0,
      max_uses: 0,
      temporary: false,
      target_type: 2,
      target_application_id: process.env.GOMOKU_ACTIVITY_APP_ID || process.env.CLIENT_ID,
    },
  });
}

client.once(Events.ClientReady, async (c) => {
  console.log(`Logged in as ${c.user.tag}`);
  await registerCommand();
  console.log('Slash command registered');
});

client.on(Events.InteractionCreate, async (interaction) => {
  if (!interaction.isChatInputCommand() || interaction.commandName !== 'gomoku') return;

  if (!interaction.guild) {
    return interaction.reply({ content: '這個指令只能在伺服器中使用。', ephemeral: true });
  }

  const selectedChannel = interaction.options.getChannel('voice_channel');
  const memberVoiceChannel = interaction.member?.voice?.channel ?? null;
  const voiceChannel = selectedChannel ?? memberVoiceChannel;

  if (!voiceChannel || voiceChannel.type !== ChannelType.GuildVoice) {
    return interaction.reply({
      content: '請先進入語音頻道，或使用 `voice_channel` 指定要開啟活動的語音頻道。',
      ephemeral: true,
    });
  }

  const permissions = voiceChannel.permissionsFor(interaction.guild.members.me);
  if (!permissions?.has([PermissionFlagsBits.CreateInstantInvite, PermissionFlagsBits.ViewChannel])) {
    return interaction.reply({
      content: '我缺少該語音頻道的 `View Channel` 或 `Create Invite` 權限。',
      ephemeral: true,
    });
  }

  await interaction.deferReply({ ephemeral: false });

  try {
    const invite = await createActivityInvite(voiceChannel.id);
    const inviteLink = `https://discord.gg/${invite.code}`;

    await interaction.editReply({
      content:
        `已在語音頻道 **${voiceChannel.name}** 建立五子棋通話活動邀請！\n` +
        `👉 ${inviteLink}\n\n` +
        '進入語音頻道後點擊連結即可開始。',
    });
  } catch (error) {
    console.error(error);
    await interaction.editReply(
      '建立活動失敗。若你是用自建 Activity，請確認 `GOMOKU_ACTIVITY_APP_ID`；否則可不填並直接使用 `CLIENT_ID`。同時確認機器人具備該頻道邀請權限。'
    );
  }
});

if (!process.env.DISCORD_TOKEN || !process.env.CLIENT_ID) {
  throw new Error('請設定 DISCORD_TOKEN 與 CLIENT_ID 環境變數。');
}

client.login(process.env.DISCORD_TOKEN);

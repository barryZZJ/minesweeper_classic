import os
import random
import re
from collections import deque

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.tensorboard import SummaryWriter


class DQN(nn.Module):
    def __init__(self, input_shape, output_size):
        super(DQN, self).__init__()
        self.conv1 = nn.Conv2d(1, 32, kernel_size=3, stride=1, padding=1)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, stride=1, padding=1)
        self.fc1 = nn.Linear(64 * input_shape[0] * input_shape[1], max(128, output_size * 2))
        self.fc2 = nn.Linear(max(128, output_size * 2), output_size)

    def forward(self, x):
        x = torch.relu(self.conv1(x))
        x = torch.relu(self.conv2(x))
        x = x.view(x.size(0), -1)
        x = torch.relu(self.fc1(x))
        x = self.fc2(x)
        return x

class DQNAgent:
    def __init__(self, input_shape, output_size, comment='', eval=False):
        self.input_shape = input_shape
        self.output_size = output_size
        self.memory = deque(maxlen=2000)
        self.gamma = 0.95    # discount rate 0.9 0.95 0.99 越大越重视未来奖励
        self.epsilon = 1.0  # exploration rate
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.999
        self.learning_rate = 0.0001  # 0.001, 0.0005, and 0.0001
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = DQN(input_shape, output_size).to(self.device)
        self.optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)
        self.criterion = nn.MSELoss()
        self.episodes = 0
        self.MAX_REWARD = 100
        self.eval = eval
        self.writer = SummaryWriter(comment=comment) if not eval else None

    def remember(self, state, action, reward, next_state, done):
        self.memory.append((state, action, reward, next_state, done))

    def act(self, state, valid_actions, force_random=False):
        if np.random.rand() <= self.epsilon or force_random:
            return random.choice(valid_actions)
        state = torch.FloatTensor(state).unsqueeze(0).unsqueeze(0).to(self.device)
        with torch.no_grad():
            act_values = self.model(state)
        return valid_actions[np.argmax([act_values[0][self._action_to_index(a, state.shape[3])].item() for a in valid_actions])]

    def _action_to_index(self, action, cols):
        return action[0] * cols + action[1]

    def train(self, batch_size):
        if len(self.memory) < batch_size:
            return
        minibatch = random.sample(self.memory, batch_size)
        avg_loss = 0
        for state, action, reward, next_state, done in minibatch:
            state = torch.FloatTensor(state).unsqueeze(0).unsqueeze(0).to(self.device)
            next_state = torch.FloatTensor(next_state).unsqueeze(0).unsqueeze(0).to(self.device)
            reward = torch.FloatTensor([reward]).to(self.device)
            target = reward
            if not done:
                target = reward + self.gamma * torch.max(self.model(next_state)[0])
            target_f = self.model(state)
            target_f[0][self._action_to_index(action, state.shape[3])] = target
            self.optimizer.zero_grad()
            loss = self.criterion(self.model(state), target_f)
            avg_loss += loss.item()
            loss.backward()
            self.optimizer.step()
        avg_loss /= batch_size
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay

        # Log metrics to TensorBoard
        self.writer.add_scalar('Loss', avg_loss, self.episodes)
        self.writer.add_scalar('Epsilon', self.epsilon, self.episodes)
        return avg_loss

    def save(self, filename):
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'epsilon': self.epsilon,
            'episodes': self.episodes,
            'memory': list(self.memory)
        }, filename)

    def load(self, checkpoint_dir, rows, cols, mines):
        checkpoint_files = [f for f in os.listdir(checkpoint_dir) if f.startswith(f"dqn_{rows}x{cols}x{mines}") and f.endswith(".pth")]
        if not checkpoint_files:
            raise FileNotFoundError("No checkpoint found in the directory.")

        # Extract episode numbers and find the file with the largest episode number
        episode_numbers = [int(re.search(r"ep(\d+)_", f).group(1)) for f in checkpoint_files]
        max_episode_file = checkpoint_files[episode_numbers.index(max(episode_numbers))]

        checkpoint_file = os.path.join(checkpoint_dir, max_episode_file)
        checkpoint = torch.load(checkpoint_file, map_location=self.device, weights_only=False)
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.epsilon = checkpoint['epsilon']
        self.episodes = checkpoint['episodes']
        self.memory = deque(checkpoint['memory'], maxlen=2000)
        self.model.train()
        print(f"Checkpoint loaded from {checkpoint_file}")

    @torch.no_grad()
    def test_play(self, env, test_episodes=100, allow_recursive=False):
        result = []
        game_revealed = []
        for ep in range(test_episodes):
            env.reset()
            reveald_cnt = 0
            lose = False
            valid_actions = [(r, c) for r in range(env.rows) for c in range(env.cols)]
            while not env.check_win() and not lose:
                state = env.get_normalized_state()
                if env.first_click:
                    action = self.act(state, valid_actions, force_random=True)
                else:
                    action = self.act(state, valid_actions)
                valid_actions.remove(action)
                row, col = action
                lose, last_revealed_cells = env.make_move(row, col, flag=False, allow_click_revealed_num=False, allow_recursive=allow_recursive, allow_retry=False)
                reveald_cnt += len(last_revealed_cells)
            result.append(lose)
            game_revealed.append(reveald_cnt)
        win_rate = result.count(False) / test_episodes
        avg_revealed_prcnt = np.average(game_revealed) / (env.rows * env.cols - env.mines) * 100
        if not self.eval:
            self.writer.add_scalar('TEST: Win rate', win_rate, self.episodes)
            self.writer.add_scalar('TEST: Avg revealed percent', avg_revealed_prcnt, self.episodes)
        return win_rate, avg_revealed_prcnt

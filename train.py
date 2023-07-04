import socket
from collections import OrderedDict
from pathlib import Path
from typing import *

import torch
import torch.nn as nn
import wandb
from tensorboardX import SummaryWriter
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm
from transformers import (
    AdamW,
    T5ForConditionalGeneration,
    T5Tokenizer,
    get_linear_schedule_with_warmup
)

import util

# Configuration details. These could be passed as command line arguments but are done this way
# for simplicity.
kname = "Text Summarization"
comment=\
    """
    <新闻文本摘要生成>
    """

k_save_dir = "./save"
k_data_dir = "./data"
# Note, the global var record_dir is used for actual saves

k_epochs = 200      # usual 200
k_model="t5-small"   # usual t5-small; could also be t5-base, t5-large, etc. But as written we support only T5
                     # to handle a different model type, change the code in main, but you might also need to change
                     # calls to forward, label config, etc.

# optim / sched
k_lr = 1e-4         # 1e-4 to 1e-5
k_adam_eps = 1e-8
k_warmup_steps = 0
#梯度的最大範圍
# 梯度的最大範圍（k_max_grad_norm）是一個用於控制梯度更新步驟的參數。
# 當梯度的範圍（即梯度的L2范數）超過這個設定的最大值時，
# 梯度將被調整或截斷，以確保它們不會變得過大
k_max_grad_norm =  1.0

# config info
k_num_train = -1      # -1 is use all
k_num_val = -1
k_batch_size = 16
k_num_workers = 4     # num of workers for dataloader

k_use_wandb = False # whether to log to wandb (you'll need to set up wandb env info)

# source and target lengths for dataloader. If you know your lengths you can change these, or
# add a collate function to handle different sizes. Depending on your inputs you should change these.
k_max_src_len = 1200
k_max_tgt_len = 120

k_seed = 42

all_config = {
    "save_dir": k_save_dir,
    "data_dir": k_data_dir,
    "epochs": k_epochs,
    "model": k_model,
    "lr": k_lr,
    "adam_eps": k_adam_eps,
    "warmup": k_warmup_steps,
    "workers": k_num_workers,
    "max grad": k_max_grad_norm,
    "num_train": k_num_train,
    "num_val": k_num_val,
    "batch_size": k_batch_size,
    "max_src_len": k_max_src_len,
    "max_tgt_len": k_max_tgt_len
}


# A dataset for our inputs.
class T5DataSet(Dataset):
    def __init__(self, tokenizer, data_dir: str, type_path, max_examples=-1,
                 max_src_len=2000, max_tgt_len=500):
        """
        max_examples: if > 0 then will load only max_examples into the dataset; -1 means use all

        max_src and max_tgt len refer to number of tokens in the input sequences
        # Note: these are not randomized. If they were we might need to collate.
        """

        valid_type_paths = ["test", "train", "val"]
        assert type_path in valid_type_paths, f"Type path must be one of {valid_type_paths}"

        self.example_path = Path(data_dir) / type_path
        self.max_examples = max_examples
        self.tokenizer = tokenizer

        self.max_src_len = max_src_len  # max num of tokens in tokenize()
        self.max_tgt_len = max_tgt_len

        self.inputs = []            # list of dict
        self.targets = []           # list of dict
        self.input_text = []        # list of str
        self.target_text = []       # list of str

        self._build()       # fill inputs, targets, max_lens

    def __len__(self):
        return len(self.inputs)

    # __getitem__方法用於根據索引從數據集中獲取一個樣本。
    def __getitem__(self, index):
        source_ids = self.inputs[index]["input_ids"].squeeze()
        target_ids = self.targets[index]["input_ids"].squeeze()

        src_mask    = self.inputs[index]["attention_mask"].squeeze()  # might need to squeeze
        target_mask = self.targets[index]["attention_mask"].squeeze()  # might need to squeeze

        src_text = self.input_text[index]
        tgt_text = self.target_text[index]

        # These will be cast to torch.long in forward
        return {"source_ids": source_ids, "source_mask": src_mask,
                "target_ids": target_ids, "target_mask": target_mask,
                "source_text": src_text, "target_text": tgt_text}

    # _build方法用於構建數據集，從源文本文件和目標文本文件中讀取文本數據。
    def _build(self):
        source_path = self.example_path.with_suffix(".source")
        target_path = self.example_path.with_suffix(".target")

        with open(source_path, 'r') as f_source, \
                open(target_path, 'r') as f_target:

            source, target = f_source.readlines(), f_target.readlines()
            source_ct, target_ct = len(source), len(target)

            # for i in range(min(source_ct, target_ct)):
            #     print("Source Line", i + 1, ":", source[i])
            #     print("Target Line", i + 1, ":", target[i])


            assert source_ct == target_ct, f"Lengths don't match"
            # Note we could batch encode
            log.warning(f'Using max_src_len, max_tgt_len = ({self.max_src_len}, {self.max_tgt_len})')

            inputs_out = []     # accumulate the output of batch_encode
            targets_out = []    # same
            inputs_text = []    # save the original text for evaluations
            targets_text = []   # same

            if self.max_examples > 0 :
                source_ct = min(self.max_examples, source_ct)

            for idx in range(source_ct):
                # append end of sequence tokens (not necessary) because handled by tokenize() call

                src = source[idx].strip()
                tgt = target[idx].strip()
                # 去除源文本和目標文本的首尾空格
                # 將處理後的文本添加到inputs_text和targets_text列表中。
                inputs_text.append(src)
                targets_text.append(tgt)

                # tokenize
                # padding="max_length" pads to max_len
                # 如果使用padding = "max_length"會將序列填充到最大長度
                # otherwise (e.g. for batch), we could use padding=longest with truncation
                # note: don't need add_special_tokens since EOS added automatically and others are PAD
                # self.tokenizer returns a dict of input_ids and attention_masks (where attn masks corresponds to padding)
                # self.tokenizer會返回一個字典，包含input_ids和attention_masks，
                # 其中注意力遮罩（attention_masks）對應填充部分
                # Note: padding could also be done via collate in dataloader
                # todo: we could actually batch encode these (i.e. multiple per)
                tokenized_inputs = self.tokenizer(
                    [src], max_length=self.max_src_len, padding="max_length", return_tensors="pt", truncation=True
                )

                # src: 要進行處理的原始文本。
                # max_length: 設定輸出的序列的最大長度。如果原始文本超過該長度，將進行截斷；如果不足該長度，將進行填充。
                # padding: 填充方式的設定。在這裡，使用 "max_length"，
                # 表示將序列填充到 max_length長度。
                # return_tensors: 設定返回的張量類型。這裡使用 "pt"
                # 表示返回PyTorch張量。
                # truncation: 是否進行截斷。在這裡，我們將文本截斷到max_length長度。
                tokenized_targets = self.tokenizer(
                    [tgt], max_length=self.max_tgt_len, padding="max_length", return_tensors="pt", truncation=True
                )
                inputs_out.append(tokenized_inputs)
                targets_out.append(tokenized_targets)
            self.inputs = inputs_out
            self.targets = targets_out
            self.input_text = inputs_text
            self.target_text = targets_text


def get_dataloaders(tokenizer, batch_size, num_train, num_val, data_dir, num_workers, shuffle_train=True,
                    shuffle_dev=False) -> Tuple[DataLoader, DataLoader]:
    """
    Returns: Tuple[train_loader : DataLoader, dev_loader : DataLoader]
    # Note:
    # - we default to not shuffling the dev set

    """
    # todo: should pass max src and max tgt len in as arguments
    train_data_set = T5DataSet(tokenizer, type_path="train", data_dir=data_dir, max_examples=num_train,
                               max_src_len=k_max_src_len, max_tgt_len=k_max_tgt_len)
    eval_data_set = T5DataSet(tokenizer, type_path="val", data_dir=data_dir, max_examples=num_val,
                              max_src_len=k_max_src_len, max_tgt_len=k_max_tgt_len)
    train_loader = DataLoader(train_data_set, batch_size=batch_size, shuffle=shuffle_train, num_workers=num_workers)
    eval_loader = DataLoader(eval_data_set, batch_size=batch_size, shuffle=shuffle_dev, num_workers=num_workers)
    log.info(f'Datasets loaded with sizes: train: {len(train_data_set)}, dev: {len(eval_data_set)}')

    return train_loader, eval_loader


def forward(model, device, batch):
    # 将批次数据中的"source_ids"取出，并将其转移到指定的计算设备上
    # （通过to(device)）。数据类型被设置为torch.long，下同。
    src_ids = batch["source_ids"].to(device, dtype=torch.long)
    src_mask = batch["source_mask"].to(device, dtype=torch.long)
    tgt_ids = batch["target_ids"].to(device, dtype=torch.long)

    # padded ids (pad=0) are set to -100, which means ignore for loss calculation
    #将"target_ids"中的值为0的填充标记（pad）替换为 - 100。
    # 这是为了在损失计算中忽略填充标记对损失的贡献。
    tgt_ids[tgt_ids[: ,:] == 0 ] = -100
    #tips：填充标记通常用值为0的特殊标记来表示
    label_ids = tgt_ids.to(device)
    # when we call model() with labels, they will be
    # - automatically right shifted by 1 (for teacher forcing)
    # "right shifted by 1"，意味着在训练过程中，模型的输入序列会向右移动一个位置，
    # 以使当前时间步的输入是上一个时间步的标签
    # - prepended by BOS=Beginning of sequence which is a PAD token
    # - any token that was -100 will be masked_fill_ to <pad> for teacher forcing
    # return_dict means return as a dictionary
    out_dict = model(src_ids, attention_mask=src_mask, labels=label_ids, return_dict=True)
    #src_ids：输入的源序列的标识符。它是一个张量（tensor），其中包含了将要输入到模型中的源序列。
    #attention_mask：源序列的注意力掩码。它是一个张量，用于指示哪些位置需要被注意力机制考虑，哪些位置应该被忽略。通常情况下，它与输入序列的长度相同，为1表示需要考虑该位置，为0表示忽略该位置。
    #labels：目标序列的标识符。它是一个张量，其中包含了模型需要预测的目标序列。在训练过程中，使用真实的目标序列作为标签进行模型的监督学习。
    #return_dict = True：这是一个布尔值参数，用于指定是否以字典的形式返回模型的输出结果。当设置为True时，模型的输出将以字典的形式返回，其中包含了各种结果，如损失值、预测结果等。如果设置为False，则模型的输出将以其他形式（如元组）返回
    loss, logits = out_dict['loss'], out_dict['logits']
    return loss, logits




def main():
    util.set_seed(k_seed)
    device, gpu_ids = util.get_available_devices()
    ###从预训练模型中加载T5条件生成模型以及分词器
    model = T5ForConditionalGeneration.from_pretrained(k_model)
    tokenizer = T5Tokenizer.from_pretrained(k_model)

    train_loader, dev_loader = \
        get_dataloaders(tokenizer, batch_size=k_batch_size, num_train=k_num_train, num_val=k_num_val,
                        data_dir=k_data_dir, num_workers=k_num_workers)

    # reset in case we used the -1 flag for all
    num_train = len(train_loader.dataset)
    num_val = len(dev_loader.dataset)
    total_steps = ( (num_train // k_batch_size) * k_epochs)     # num times that optim.step() will be called
    total_train = num_train * k_epochs

    model.to(device)

    optimizer = AdamW(model.parameters(), lr=k_lr, eps=k_adam_eps)
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=k_warmup_steps,
                                                num_training_steps=total_steps)

    log.info(f'device: {device}\n'
             f'gpu_ids: {gpu_ids}\n'
             f'total_steps: {total_steps}\n'
             f'total_train (num_t * epoch): {total_train}\n'
             f'machine: {socket.gethostname()}\n')

    config_str = "\n"
    for k, v in all_config.items():
        config_str += f'{k}: {v}\n'
    config_str += f'record_dir: {record_dir}\n'
    log.info(config_str)

    epoch = 0       # number of times we have passed through entire set of training examples
    step = 0        # number of total examples we have done (will be epoch * len(data_set) at end of each epoch)
    while epoch < k_epochs:
        epoch += 1
        model.train()
        #tqdm用于创建进度条
        with torch.enable_grad(), tqdm(total=num_train) as progress_bar:
            for batch_num, batch in enumerate(train_loader):
                batch_size = len(batch["source_ids"])
                loss, logits = forward(model, device, batch)
                loss_val = loss.item()      # get the item since loss is a tensor

                # Backward
                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), k_max_grad_norm)
                optimizer.step()
                scheduler.step()        # don't need to pass step to scheduler

                # Log info
                step += batch_size
                progress_bar.update(batch_size)
                progress_bar.set_postfix(epoch=epoch,
                                         loss=loss_val)
                tbx.add_scalar('train/loss', loss_val, step)
                tbx.add_scalar('train/LR',
                               optimizer.param_groups[0]['lr'],
                               step)

        ###############
        # Evaluate (you might want to save checkpoints)
        ###############
        log.info(f'Evaluating at step {step}...')
        model.eval()        # put model in eval mode

        # See how the model is doing with exact match on tokens
        pred_list_all = []                      # accumulate for saving; list; one list per epoch
        pred_list_correct = []
        loss_meter = util.AverageMeter()    # NLL (default metric for model) (reset each time)

        # set up two count variables
        total_matches_no_eos_ct = 0
        total_matches_with_eos_ct = 0

        with torch.no_grad(), \
             tqdm(total=num_val) as progress_bar:
            for batch_num, batch in enumerate(dev_loader):
                batch_size = len(batch["source_ids"])

                # evaluation for loss fcn
                loss, _ = forward(model, device, batch)     # loss, logits, but don't need logits
                loss_meter.update(loss.item(), batch_size)  # loss.item() since it's a tensor

                # predict / generate for token matches
                src_ids = batch["source_ids"].to(device, dtype=torch.long)
                src_mask = batch["source_mask"].to(device, dtype=torch.long)
                tgt_ids = batch["target_ids"].to(device, dtype=torch.long)
                # note you could tweak the generation params. See huggingface details for generate
                generated_ids = model.generate(src_ids, attention_mask=src_mask)       # (batch x seq length)

                # collect some stats
                total_matches_no_eos, total_matches_with_eos, correct_indices = \
                    util.masked_token_match(tgt_ids, generated_ids, return_indices=True)
                total_matches_no_eos_ct += total_matches_no_eos
                total_matches_with_eos_ct += total_matches_with_eos

                # save for qualitative analysis
                orig_text_input, orig_text_output = batch["source_text"], batch["target_text"]
                # todo: this could break once skip_special_tokens is fixed
                outputs_decoded = tokenizer.batch_decode(generated_ids, skip_special_tokens=False)
                preds = list(zip(orig_text_input, orig_text_output, outputs_decoded))
                pred_list_all.extend(preds)

                # we also store only the correct indices
                for idx in correct_indices.tolist():    # tensor to list; these are the valid indices
                    pred_list_correct.append(preds[idx[0]])     # each item was a list of one element

                # print one batch of generations for qualitative assessment
                if batch_num == 0:
                    for orig_input, orig_target, actual_output in preds[:1]:
                        log.info(f'Source: {orig_input}\t Target: {orig_target}\n'
                                 f'\t Actual: {actual_output}')

                # Log info
                progress_bar.update(batch_size)
                progress_bar.set_postfix(NLL=loss_meter.avg)

        # save predictions for qualititative analysis
        util.save_preds(pred_list_all, record_dir)
        util.save_preds(pred_list_correct, record_dir, file_name="preds_correct.csv")
        results_list = [('NLL', loss_meter.avg),
                        ('exact_match_with_eos', total_matches_with_eos_ct),
                        ('exact_match_no_eos', total_matches_no_eos_ct)]
        results = OrderedDict(results_list)

        # Log to console
        results_str = ', '.join(f'{k}: {v:05.2f}' for k, v in results.items())
        log.info(f'Dev {results_str}')

        # Log to TensorBoard
        for k, v in results.items():
            tbx.add_scalar(f'dev/{k}', v, step)
        util.visualize(tbx,
                       pred_dict=pred_list_all,     # will be truncated by num_visuals
                       step=step,
                       split='dev',
                       num_visuals=3)


if __name__ == '__main__':
    name = kname
    if k_use_wandb:
        wandb.init()
        record_dir = wandb.run.dir
        wandb.tensorboard.patch(save=True, tensorboardX=True)
    else:
        record_dir = util.get_save_dir(k_save_dir, name)

    log = util.get_logger(record_dir, "root", "debug")
    tbx = SummaryWriter(record_dir, flush_secs=5)
    log.info(name)
    log.info(comment)
    main()

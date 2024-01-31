import torch
import torch.nn as nn
from torch.nn import functional as F
from torch.utils.data import Dataset, DataLoader, Subset
import requests
import os
import csv
import argparse
from utils import *
import transformers
from datasets import load_dataset
#from torch.utils.tensorboard import SummaryWriter
from tokenizers import Tokenizer
from transformers import GPT2Tokenizer, GPT2Model, AutoTokenizer
import time
import numpy as np

data_cache_dir = "~/datasets" #"/ram/tmp"
dataset = 'stories' # This still needs to be set manually

# Set seed
torch.manual_seed(1337)

if dataset == 'shakespeare':
    @torch.no_grad()
    def estimate_loss(model):
        out = {}
        model.eval()
        # Test loss
        losses=[]
        for itr,batch in enumerate(test_loader):
            if itr==args.eval_iters:
                break
            data = tokenizer(batch,padding="max_length",truncation=True,max_length=block_size,return_tensors="pt")        
            # data = data['input_ids']
            data = data.to(device)
            xb,yb = data[:, :-1], data[:, 1:]
            logits, loss = model(xb, yb)
            losses.append(loss.item())
        out['test'] = np.mean(losses)

        # Train loss
        losses=[]
        for itr,batch in enumerate(train_loader):
            if itr==args.eval_iters:
                break
            data = tokenizer(batch,padding="max_length",truncation=True,max_length=block_size,return_tensors="pt")        
            # data = data['input_ids']
            data = data.to(device)
            xb,yb = data[:, :-1], data[:, 1:]
            logits, loss = model(xb, yb)
            losses.append(loss.item())
        out['train'] = np.mean(losses)
        model.train()
        return out
    
elif dataset == 'stories':
    @torch.no_grad()
    def estimate_loss(model):
        out = {}
        model.eval()
        # Test loss
        losses=[]
        for itr,batch in enumerate(test_loader):
            if itr==args.eval_iters:
                break
            data = tokenizer(batch['text'],padding="max_length",truncation=True,max_length=block_size+1,return_tensors="pt")        
            data = data['input_ids']
            data = data.to(device)
            xb,yb = data[:, :-1], data[:, 1:]
            logits, loss = model(xb, yb)
            losses.append(loss.item())

        out['test'] = np.mean(losses)

        # Train loss
        losses=[]
        for itr,batch in enumerate(train_loader):
            if itr==args.eval_iters:
                break
            data = tokenizer(batch['text'],padding="max_length",truncation=True,max_length=block_size+1,return_tensors="pt")        
            data = data['input_ids']
            data = data.to(device)
            xb,yb = data[:, :-1], data[:, 1:]
            logits, loss = model(xb, yb)
            losses.append(loss.item())

        out['train'] = np.mean(losses)
        # out['train'] = 0
        model.train()
        return out


if __name__ == '__main__':
    #torch.autograd.set_detect_anomaly(True)
    parser = argparse.ArgumentParser()

    # Parameters
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    parser.add_argument('--batch-size', type=int, default=64, help='Specify the batch size')
    parser.add_argument('--eval-interval', type=int, default=1000, help='Specify the evaluation interval')
    parser.add_argument('--eval-iters', type=int, default=500, help='Specify the evaluation iterations')

    parser.add_argument('--block-size', type=int, default=256, help='Specify the block size')        
    parser.add_argument('--dm', type=int, default=512, help='Specify embedding dimension')
    parser.add_argument('--dk', type=int, default=64, help='Specify dimension of key/query vectors')
    parser.add_argument('--dv', type=int, default=64, help='Specify dimension of value vectors')
    parser.add_argument('--h', type=int, default=8, help='Specify the number of heads')
    parser.add_argument('--N', type=int, default=6, help='Specify the number of layers')
    
    parser.add_argument('--norm-type', type=str, default='layer', help='Type of normalization layer to use ("layer" for LayerNorm, "rms" for RMSNorm)')
    parser.add_argument('--post-norm', type=int, default=1, help='Whether to use post layer normalization')
    parser.add_argument('--final-norm', type=str, default='layer', help='Norm to use in final layer ("layer" for LayerNorm, "rms" for RMSNorm)')
    parser.add_argument('--rectify', type=int, default=0, help='Whether to use rectified attention')
    parser.add_argument('--dropout', type=float, default=0.2, help='Specify the dropout')
    parser.add_argument('--attention-type', type=str, default='sdp', help='Type of attention to use ("sdp" for scaled dot product, "other" for other types)')
    parser.add_argument('--block-architecture', type=str, default='series', help='Type of block architecture to use ("series" for series of blocks, "parallel" for parallel blocks)')

    parser.add_argument('--lr', type=float, default=1e-3, help='Specify the learning rate')
    parser.add_argument('--device', type=str, default=device, help='Specify the device')
    parser.add_argument('--n-itrs', type=int, default=20001, help='Specify the number of iterations')
    parser.add_argument('--filepath', type=str,default='original.csv', help='Specify the file path')
    parser.add_argument('--dataset', type=str,default='stories', help='Specify the dataset')
    parser.add_argument('--stream-data',action='store_true', help='Whether to stream data from disk')
    parser.add_argument('--version', type=int,default=0, help='For saving the model with distinct names')
    args = parser.parse_args()

    # version = args.block_type
    version = args.version
    block_size=args.block_size

    # if args.dataset == 'shakespeare':
    #     # Download a sample text file (e.g., "The Complete Works of William Shakespeare")
    #     url = "https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt"
    #     file_path = "datasets/shakespeare.txt"

    #     if not os.path.exists(file_path):
    #         response = requests.get(url)
    #         with open(file_path, 'w') as file:
    #             file.write(response.text)

    #     # Read in text file
    #     with open(file_path,'r',encoding='utf-8') as f:
    #         text = f.read()

    #     # Split up text
    #     n = len(text)
    #     print("total length of text is ", n)
    #     test_text = text[:n//10]
    #     train_text = text[n//10:] 
    #     shakespeare_train_data = TextDataFromFile(text=train_text,block_size=block_size+1)
    #     shakespeare_test_data = TextDataFromFile(text=test_text,block_size=block_size+1)
    #     test_loader = DataLoader(shakespeare_test_data, batch_size=args.batch_size, shuffle=False)
    #     train_loader = DataLoader(shakespeare_train_data, batch_size=args.batch_size, shuffle=True)
    #     tokenizer = CharacterTokenizer(block_size=block_size+1)

    #     # shakespeare_data = TextDataFromFile(block_size=block_size+1,file_path=file_path)
    #     # N = len(shakespeare_data)
    #     # test_set = Subset(shakespeare_data, [i for i in range(N) if i % 10 == 0])
    #     # train_set = Subset(shakespeare_data, [i for i in range(N) if i % 10 != 0])
    #     # test_loader = DataLoader(test_set, batch_size=args.batch_size, shuffle=False)
    #     # train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True)
    #     # tokenizer = CharacterTokenizer(block_size=block_size+1)

    # elif args.dataset == 'stories':
    #     # vocab_size=50258
    #     train_set = load_dataset("nRuaif/tinystories-gpt4",cache_dir=data_cache_dir,split='train')
    #     train_loader = DataLoader(train_set, batch_size=64)
    #     test_set = load_dataset("nRuaif/tinystories-gpt4",cache_dir=data_cache_dir,split='test')
    #     test_loader = DataLoader(test_set, batch_size=64)
    #     # tokenizer = AutoTokenizer.from_pretrained("georgeyw/TinyStories-tokenizer-10k")
    #     tokenizer = AutoTokenizer.from_pretrained("georgeyw/TinyStories-tokenizer-5k")
    #     tokenizer.add_special_tokens({'pad_token': '[PAD]'})

    # elif args.dataset == 'wikitext103':
    #     train_set = load_dataset("wikitext",'wikitext-103-v1',cache_dir=data_cache_dir,split='train')
    #     train_loader = DataLoader(train_set, batch_size=64)
    #     test_set = load_dataset("wikitext",'wikitext-103-v1',cache_dir=data_cache_dir,split='test')
    #     test_loader = DataLoader(test_set, batch_size=64)
    #     tokenizer = AutoTokenizer.from_pretrained("gpt2")
######################################################################

    # from torch.nn.utils.rnn import pad_sequence

    # Choose the dataset

    # Load the dataset
    if args.dataset == 'shakespeare':
        # Download a sample text file (e.g., "The Complete Works of William Shakespeare")
        url = "https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt"
        file_path = "datasets/shakespeare.txt"

        if not os.path.exists(file_path):
            response = requests.get(url)
            with open(file_path, 'w') as file:
                file.write(response.text)

        # Read in text file
        with open(file_path,'r',encoding='utf-8') as f:
            text = f.read()

        # Split up text
        n = len(text)
        print("total length of text is ", n)
        test_text = text[:n//10]
        train_text = text[n//10:] 
        train_set = TextDataFromFile(text=train_text,block_size=block_size+1)
        test_set = TextDataFromFile(text=test_text,block_size=block_size+1)
    elif args.dataset == 'stories': # Working
        train_set = load_dataset("nRuaif/tinystories-gpt4",cache_dir=data_cache_dir,split='train',streaming=args.stream_data)
        test_set = load_dataset("nRuaif/tinystories-gpt4",cache_dir=data_cache_dir,split='test',streaming=args.stream_data)
        # tokenizer = AutoTokenizer.from_pretrained("georgeyw/TinyStories-tokenizer-10k")
        # tokenizer.add_special_tokens({'pad_token': '[PAD]'})
    elif args.dataset == 'wikitext103': # Working
        train_set = load_dataset("wikitext",'wikitext-103-v1',cache_dir=data_cache_dir,split='train',streaming=args.stream_data)
        test_set = load_dataset("wikitext",'wikitext-103-v1',cache_dir=data_cache_dir,split='test',streaming=args.stream_data)
    elif args.dataset == "wikitext2": # Working
        # dataset = load_dataset("wikitext", "wikitext-2-v1")
        train_set = load_dataset("wikitext",'wikitext-2-v1',cache_dir=data_cache_dir,split='train',streaming=args.stream_data)
        test_set = load_dataset("wikitext",'wikitext-2-v1',cache_dir=data_cache_dir,split='test',streaming=args.stream_data)
    elif args.dataset == "simple_wiki": # There is not test split...
        # train_set = load_dataset("wikipedia",'20200501.simple',cache_dir=data_cache_dir,split='train',streaming=args.stream_data)
        # test_set = load_dataset("wikipedia",'20200501.simple',cache_dir=data_cache_dir,split='test',streaming=args.stream_data)
        train_set = load_dataset("wikipedia","20220301.en",cache_dir=data_cache_dir,split='train',streaming=args.stream_data)
        test_set = load_dataset("wikipedia","20220301.en",cache_dir=data_cache_dir,split='train',streaming=args.stream_data)
    elif args.dataset == "cbt":
        # dataset = load_dataset("cbt", "CN")
        train_set = load_dataset("cbt",'CN',cache_dir=data_cache_dir,split='train',streaming=args.stream_data)
        test_set = load_dataset("cbt",'CN',cache_dir=data_cache_dir,split='test',streaming=args.stream_data)
    elif args.dataset == "ptb":
        # dataset = load_dataset("ptb_text_only")
        train_set = load_dataset("ptb_text_only",'train',cache_dir=data_cache_dir,streaming=args.stream_data)
        test_set = load_dataset("ptb_text_only",'test',cache_dir=data_cache_dir,streaming=args.stream_data)
    # elif args.dataset == "brown":
    #     # dataset = load_dataset("brown")
    #     train_set = load_dataset("brown",'train',cache_dir=data_cache_dir,streaming=args.stream_data)
    #     test_set = load_dataset("brown",'test',cache_dir=data_cache_dir,streaming=args.stream_data)

    # Make dataloaders
    train_loader = DataLoader(train_set, batch_size=args.batch_size) # shuffle=True
    test_loader = DataLoader(test_set, batch_size=args.batch_size) # shuffle=False

    # Select an appropriate tokenizer
    if args.dataset in ["wikitext2", "simple_wiki", "cbt"]:
        tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
    elif args.dataset in ["ptb","wikitext103"]:
        tokenizer = AutoTokenizer.from_pretrained("gpt2")  # GPT-2 tokenizer works well with PTB
    elif args.dataset == "brown":
        tokenizer = AutoTokenizer.from_pretrained("roberta-base")
    elif args.dataset == "stories":
        tokenizer = AutoTokenizer.from_pretrained("georgeyw/TinyStories-tokenizer-5k")
        # tokenizer.add_special_tokens({'pad_token': '[PAD]'})
    elif args.dataset == "shakespeare":
        tokenizer = CharacterTokenizer(block_size=block_size+1)
    
    tokenizer.add_special_tokens({'pad_token': '[PAD]'})

    assert(0)
    # # Tokenize the dataset
    # def tokenize_function(examples):
    #     return tokenizer(examples["text"], padding="max_length", truncation=True, max_length=512)

    # tokenized_datasets = dataset.map(tokenize_function, batched=True)

    # # Create a DataLoader
    # def collate_fn(batch):
    #     input_ids = [item["input_ids"] for item in batch]
    #     input_ids = pad_sequence([torch.tensor(ids) for ids in input_ids], batch_first=True, padding_value=tokenizer.pad_token_id)
    #     attention_mask = [item["attention_mask"] for item in batch]
    #     attention_mask = pad_sequence([torch.tensor(mask) for mask in attention_mask], batch_first=True, padding_value=0)
    #     return {"input_ids": input_ids, "attention_mask": attention_mask}

    # dataloader = DataLoader(tokenized_datasets["train"], batch_size=32, collate_fn=collate_fn)

    # # Example: Iterate over the dataloader
    # for batch in dataloader:
    #     print(batch)
    #     break  # Remove this line to iterate over the entire dataloader

    ##################################################################
    vocab_size=len(tokenizer)
    decode = tokenizer.decode

    filepath = args.filepath
    # args_dict = vars(args)
    args_dict = {k: v for k, v in vars(args).items() if v is not None}
    args_dict['vocab_size'] = vocab_size

    # Make / load model
    if os.path.exists('transformer_' + str(version) + '.pt'):
        model = torch.load('transformer_' + str(version) + '.pt')
    else:
        # model = Transformer(**args_dict)
        model = Transformer(vocab_size=vocab_size,dm=args.dm,dk=args.dk,dv=args.dv,block_size=args.block_size,h=args.h,N=args.N,final_norm=args.final_norm,norm_type=args.norm_type, post_norm=args.post_norm, rectify=args.rectify,dropout=args.dropout,block_architecture=args.block_architecture,attention_type=args.attention_type)
 

    print(sum(p.numel() for p in model.parameters())/1e6, 'M parameters')
    m=model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    
    # # Visualize model
    # m.logits_only=True
    # writer = SummaryWriter()
    # dummy_input = torch.zeros((1, block_size), device=device, dtype=torch.long)
    # writer.add_graph(m, dummy_input)
    # writer.close()
    # m.logits_only=False

    if args.dataset == 'shakespeare':
        # Train
        for itr,batch in enumerate(train_loader):
            data = tokenizer(batch,padding="max_length",truncation=True,max_length=block_size,return_tensors="pt")    
            xb,yb = data[:,:-1],data[:,1:]
            logits, loss = model(xb, yb)
            if itr % args.eval_interval == 0:
                losses = estimate_loss(model)  # Calculate loss
                with open(filepath, 'a', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow([losses[split] for split in ['train','test']])
                idx = torch.zeros((1, block_size), device=device, dtype=torch.long)
                idx = m.generate(idx, 500)
                print("\nSample: \n", decode(list(idx[0])[block_size:]), '\n\n')
                print(f"step {itr}: train loss {losses['train']:.4f}, val loss {losses['test']:.4f}")
                torch.save(m, 'transformer_' + str(version) + '.pt')
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()

    # elif args.dataset == 'stories':
    else:
        tic = time.time()
        # TinyStories version that I am currently working on
        for itr,batch in enumerate(train_loader):
            data = tokenizer(batch['text'],padding="max_length",truncation=True,max_length=block_size+1,return_tensors="pt")        
            data = data['input_ids']
            data = data.to(device)
            xb,yb = data[:, :-1], data[:, 1:]
            if itr % args.eval_interval == 0:
                elapsed, tic = time.time() - tic, time.time()
                print(f"step {itr}: {elapsed:.2f} seconds")
                losses = estimate_loss(model)  # Calculate loss
                with open(filepath, 'a', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow([losses[split] for split in ['train','test']])
                idx = torch.zeros((1, args.block_size), device=device, dtype=torch.long)
                idx = m.generate(idx, 500,beta=2.0)
                print("\nSample: \n", decode(list(idx[0])[args.block_size:]), '\n\n')
                print(f"step {itr}: train loss {losses['train']:.4f}, val loss {losses['test']:.4f}")
                torch.save(m, 'transformer_' + str(version) + '.pt')
            logits, loss = model(xb, yb)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()

    torch.save(m,'transformer_'+str(args.version)+'.pt')
    idx=torch.zeros((1,block_size),device=device,dtype=torch.long)
    idx=m.generate(idx,5000)
    print(idx)
    print(decode(list(idx[0])[args.block_size:]))
